import { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import './App.css'

// Ensure this matches your backend URL
const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

const titleCaseAmenity = (type) =>
  type
    .replace(/([A-Z])/g, ' $1')
    .trim()
    .replace(/^./, (char) => char.toUpperCase())

const starDisplay = (value = 0) => {
  const rounded = Math.round(value)
  return '★'.repeat(rounded).padEnd(5, '☆')
}

const amenityColors = {
  WaterFountain: '#0ea5e9',
  Bathroom: '#8b5cf6',
  VendingMachine: '#f97316',
}

export default function App() {
  const mapNodeRef = useRef(null)
  const mapInstanceRef = useRef(null)
  const markersRef = useRef([]) // Keep track of markers to clear them on search
  
  // -- State --
  const [amenities, setAmenities] = useState([])
  const [selectedAmenity, setSelectedAmenity] = useState(null)
  const [searchTerm, setSearchTerm] = useState('')
  
  // Rating State
  const [userRating, setUserRating] = useState(0)
  const [hoverRating, setHoverRating] = useState(0)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [submitMessage, setSubmitMessage] = useState(null)

  // Leaderboard State
  const [showLeaderboard, setShowLeaderboard] = useState(false)
  const [activeTab, setActiveTab] = useState('clean-bathrooms')
  const [leaderboardData, setLeaderboardData] = useState({
    'clean-bathrooms': [],
    'coldest-fountains': [],
    'overall': []
  })
  const [loadingLeaderboard, setLoadingLeaderboard] = useState(false)

  // Extras Popup State
  const [showExtras, setShowExtras] = useState(false)
  const [activeExtraSection, setActiveExtraSection] = useState('building')
  
  // Form states for CRUD operations
  const [buildingForm, setBuildingForm] = useState({ name: '', address: '', lat: '', lon: '' })
  const [amenityForm, setAmenityForm] = useState({ building_id: '', type: '', floor: '', notes: '' })
  const [tagForm, setTagForm] = useState({ label: '' })
  const [deleteId, setDeleteId] = useState({ building: '', amenity: '', tag: '' })
  const [updateForm, setUpdateForm] = useState({ 
    building: { id: '', name: '', address_id: '' },
    amenity: { id: '', building_id: '', type: '', floor: '', notes: '' },
    tag: { id: '', label: '' }
  })
  const [extrasMessage, setExtrasMessage] = useState(null)
  const [buildingsList, setBuildingsList] = useState([])
  const [tagsList, setTagsList] = useState([])

  // -- 1. Fetch Data from Backend (Search Integration) --
  const fetchAmenities = async (keyword = '') => {
    try {
      const url = new URL(`${API_BASE}/amenities?limit=1500`)
      // If keyword exists, append it to URL
      if (keyword) url.searchParams.append('keyword', keyword)
      
      const res = await fetch(url)
      if (!res.ok) throw new Error('Failed to fetch')
      
      const data = await res.json()
      
      // Transform SQL flat response to UI structure
      const transformed = data.map(item => ({
        amenityId: item.amenityid,
        buildingId: item.buildingid,
        type: item.type,
        floor: item.floor,
        notes: item.notes,
        building: { name: item.building_name },
        address: { address: item.address, lat: item.lat || 40.1096, lon: item.lon || -88.2272 }, // Fallback coords if missing in DB response
        review: {
          avgRating: item.avg_rating,
          reviewCount: item.review_count
        }
      }))
      
      setAmenities(transformed)
    } catch (err) {
      console.error("Error loading amenities:", err)
    }
  }

  // Initial load
  useEffect(() => {
    fetchAmenities()
  }, [])

  // -- 2. Map Initialization & Marker Updates --
  useEffect(() => {
    if (!mapNodeRef.current) return

    // Initialize map only once
    if (!mapInstanceRef.current) {
      const map = L.map(mapNodeRef.current, {
        scrollWheelZoom: true,
        zoomControl: true,
      }).setView([40.1096, -88.2273], 14.5)

      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '&copy; OpenStreetMap contributors',
      }).addTo(map)

      mapInstanceRef.current = map
    }

    const map = mapInstanceRef.current

    // Clear existing markers
    markersRef.current.forEach(m => map.removeLayer(m))
    markersRef.current = []

    // Add new markers
    amenities.forEach((amenity) => {
      const { address, building } = amenity
      // Only plot if we have valid coordinates (Note: your SQL query needs to return lat/lon!)
      // I noticed your backend query didn't select lat/lon, I will fix that in the backend instructions below.
      if (!address || !address.lat || !address.lon) return

      const color = amenityColors[amenity.type] ?? '#0f172a'

      const marker = L.circleMarker([address.lat, address.lon], {
        radius: 10,
        color,
        weight: 2,
        fillColor: color,
        fillOpacity: 0.85,
      }).addTo(map)

      marker.on('click', () => {
        setSelectedAmenity(amenity)
        setUserRating(0)
        setHoverRating(0)
        setSubmitMessage(null)
      })

      marker.bindPopup(
        `<article class="popup">
          <h3>${building.name}</h3>
          <p class="type">${titleCaseAmenity(amenity.type)} - Floor ${amenity.floor}</p>
          <p class="address">${address.address}</p>
          <p class="id-info-popup"><strong>Building ID:</strong> ${amenity.buildingId ?? 'N/A'}</p>
          <p class="id-info-popup"><strong>Amenity ID:</strong> ${amenity.amenityId ?? 'N/A'}</p>
        </article>`
      )

      markersRef.current.push(marker)
    })

  }, [amenities])

  // -- 3. Handle Search Submit --
  const handleSearch = (e) => {
    e.preventDefault()
    fetchAmenities(searchTerm)
  }

  // -- 5. Fetch Leaderboard Data --
  const fetchLeaderboard = async (tab) => {
    setLoadingLeaderboard(true)
    try {
      let endpoint = ''
      if (tab === 'clean-bathrooms') {
        endpoint = '/leaderboard/clean-bathrooms-vending'
      } else if (tab === 'coldest-fountains') {
        endpoint = '/leaderboard/coldest-fountains'
      } else if (tab === 'overall') {
        endpoint = '/leaderboard/overall-amenities'
      }

      const res = await fetch(`${API_BASE}${endpoint}`)
      if (!res.ok) throw new Error('Failed to fetch leaderboard')
      const data = await res.json()
      setLeaderboardData(prev => ({ ...prev, [tab]: data }))
    } catch (err) {
      console.error('Error loading leaderboard:', err)
    } finally {
      setLoadingLeaderboard(false)
    }
  }

  // Load leaderboard when tab changes
  useEffect(() => {
    if (showLeaderboard && !leaderboardData[activeTab].length) {
      fetchLeaderboard(activeTab)
    }
  }, [showLeaderboard, activeTab])

  // Fetch lists for Extras popup
  const fetchBuildings = async () => {
    try {
      const res = await fetch(`${API_BASE}/buildings?limit=500`)
      if (res.ok) {
        const data = await res.json()
        setBuildingsList(data)
      }
    } catch (err) {
      console.error('Error fetching buildings:', err)
    }
  }

  const fetchTags = async () => {
    try {
      const res = await fetch(`${API_BASE}/tags`)
      if (res.ok) {
        const data = await res.json()
        setTagsList(data)
      }
    } catch (err) {
      console.error('Error fetching tags:', err)
    }
  }

  // Load data when Extras popup opens
  useEffect(() => {
    if (showExtras) {
      fetchBuildings()
      fetchTags()
    }
  }, [showExtras])

  // Building CRUD operations
  const handleCreateBuilding = async (e) => {
    e.preventDefault()
    setExtrasMessage(null)
    try {
      const res = await fetch(`${API_BASE}/buildings/with-address`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: buildingForm.name,
          address: buildingForm.address,
          lat: parseFloat(buildingForm.lat),
          lon: parseFloat(buildingForm.lon)
        })
      })
      if (!res.ok) {
        // Try to get the error detail from the response
        const errorData = await res.json().catch(() => ({ detail: 'Unknown error' }))
        throw new Error(errorData.detail || `HTTP ${res.status}: Failed to create building`)
      }
      const result = await res.json()
      setExtrasMessage({ type: 'success', text: 'Building created successfully!' })
      setBuildingForm({ name: '', address: '', lat: '', lon: '' })
      fetchBuildings()
      fetchAmenities(searchTerm)
    } catch (err) {
      setExtrasMessage({ type: 'error', text: err.message || 'Failed to create building' })
    }
  }

  const handleDeleteBuilding = async (e) => {
    e.preventDefault()
    setExtrasMessage(null)
    if (!deleteId.building) {
      setExtrasMessage({ type: 'error', text: 'Please enter a building ID' })
      return
    }
    try {
      const res = await fetch(`${API_BASE}/buildings/${deleteId.building}`, {
        method: 'DELETE'
      })
      if (!res.ok) throw new Error('Failed to delete building')
      setExtrasMessage({ type: 'success', text: 'Building deleted successfully!' })
      setDeleteId({ ...deleteId, building: '' })
      fetchBuildings()
      fetchAmenities(searchTerm)
    } catch (err) {
      setExtrasMessage({ type: 'error', text: err.message || 'Failed to delete building' })
    }
  }

  const handleUpdateBuilding = async (e) => {
    e.preventDefault()
    setExtrasMessage(null)
    if (!updateForm.building.id) {
      setExtrasMessage({ type: 'error', text: 'Please enter a building ID' })
      return
    }
    try {
      const payload = {}
      if (updateForm.building.name) payload.name = updateForm.building.name
      if (updateForm.building.address_id) payload.address_id = parseInt(updateForm.building.address_id)
      
      if (Object.keys(payload).length === 0) {
        setExtrasMessage({ type: 'error', text: 'Please provide at least one field to update' })
        return
      }

      const res = await fetch(`${API_BASE}/buildings/${updateForm.building.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
      if (!res.ok) throw new Error('Failed to update building')
      setExtrasMessage({ type: 'success', text: 'Building updated successfully!' })
      setUpdateForm({ ...updateForm, building: { id: '', name: '', address_id: '' } })
      fetchBuildings()
      fetchAmenities(searchTerm)
    } catch (err) {
      setExtrasMessage({ type: 'error', text: err.message || 'Failed to update building' })
    }
  }

  // Amenity CRUD operations
  const handleCreateAmenity = async (e) => {
    e.preventDefault()
    setExtrasMessage(null)
    try {
      const res = await fetch(`${API_BASE}/amenities`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          building_id: parseInt(amenityForm.building_id),
          type: amenityForm.type,
          floor: amenityForm.floor,
          notes: amenityForm.notes || null
        })
      })
      if (!res.ok) throw new Error('Failed to create amenity')
      setExtrasMessage({ type: 'success', text: 'Amenity created successfully!' })
      setAmenityForm({ building_id: '', type: '', floor: '', notes: '' })
      fetchAmenities(searchTerm)
    } catch (err) {
      setExtrasMessage({ type: 'error', text: err.message || 'Failed to create amenity' })
    }
  }

  const handleDeleteAmenity = async (e) => {
    e.preventDefault()
    setExtrasMessage(null)
    if (!deleteId.amenity) {
      setExtrasMessage({ type: 'error', text: 'Please enter an amenity ID' })
      return
    }
    try {
      const res = await fetch(`${API_BASE}/amenities/${deleteId.amenity}`, {
        method: 'DELETE'
      })
      if (!res.ok) throw new Error('Failed to delete amenity')
      setExtrasMessage({ type: 'success', text: 'Amenity deleted successfully!' })
      setDeleteId({ ...deleteId, amenity: '' })
      fetchAmenities(searchTerm)
    } catch (err) {
      setExtrasMessage({ type: 'error', text: err.message || 'Failed to delete amenity' })
    }
  }

  const handleUpdateAmenity = async (e) => {
    e.preventDefault()
    setExtrasMessage(null)
    if (!updateForm.amenity.id) {
      setExtrasMessage({ type: 'error', text: 'Please enter an amenity ID' })
      return
    }
    try {
      const payload = {}
      if (updateForm.amenity.building_id) payload.building_id = parseInt(updateForm.amenity.building_id)
      if (updateForm.amenity.type) payload.type = updateForm.amenity.type
      if (updateForm.amenity.floor) payload.floor = updateForm.amenity.floor
      if (updateForm.amenity.notes !== undefined) payload.notes = updateForm.amenity.notes || null
      
      if (Object.keys(payload).length === 0) {
        setExtrasMessage({ type: 'error', text: 'Please provide at least one field to update' })
        return
      }

      const res = await fetch(`${API_BASE}/amenities/${updateForm.amenity.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
      if (!res.ok) throw new Error('Failed to update amenity')
      setExtrasMessage({ type: 'success', text: 'Amenity updated successfully!' })
      setUpdateForm({ ...updateForm, amenity: { id: '', building_id: '', type: '', floor: '', notes: '' } })
      fetchAmenities(searchTerm)
    } catch (err) {
      setExtrasMessage({ type: 'error', text: err.message || 'Failed to update amenity' })
    }
  }

  // Tag CRUD operations
  const handleCreateTag = async (e) => {
    e.preventDefault()
    setExtrasMessage(null)
    try {
      const res = await fetch(`${API_BASE}/tags`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ label: tagForm.label })
      })
      if (!res.ok) throw new Error('Failed to create tag')
      setExtrasMessage({ type: 'success', text: 'Tag created successfully!' })
      setTagForm({ label: '' })
      fetchTags()
    } catch (err) {
      setExtrasMessage({ type: 'error', text: err.message || 'Failed to create tag' })
    }
  }

  const handleDeleteTag = async (e) => {
    e.preventDefault()
    setExtrasMessage(null)
    if (!deleteId.tag) {
      setExtrasMessage({ type: 'error', text: 'Please enter a tag ID' })
      return
    }
    try {
      const res = await fetch(`${API_BASE}/tags/${deleteId.tag}`, {
        method: 'DELETE'
      })
      if (!res.ok) throw new Error('Failed to delete tag')
      setExtrasMessage({ type: 'success', text: 'Tag deleted successfully!' })
      setDeleteId({ ...deleteId, tag: '' })
      fetchTags()
    } catch (err) {
      setExtrasMessage({ type: 'error', text: err.message || 'Failed to delete tag' })
    }
  }

  const handleUpdateTag = async (e) => {
    e.preventDefault()
    setExtrasMessage(null)
    if (!updateForm.tag.id || !updateForm.tag.label) {
      setExtrasMessage({ type: 'error', text: 'Please enter tag ID and new label' })
      return
    }
    try {
      const res = await fetch(`${API_BASE}/tags/${updateForm.tag.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ label: updateForm.tag.label })
      })
      if (!res.ok) throw new Error('Failed to update tag')
      setExtrasMessage({ type: 'success', text: 'Tag updated successfully!' })
      setUpdateForm({ ...updateForm, tag: { id: '', label: '' } })
      fetchTags()
    } catch (err) {
      setExtrasMessage({ type: 'error', text: err.message || 'Failed to update tag' })
    }
  }


  // -- 4. Handle Review Submission (Updated to POST) --
  const handleRatingSubmit = async () => {
    if (!selectedAmenity) return
    if (userRating === 0) {
      setSubmitMessage({ type: 'error', text: 'Pick a star rating first.' })
      return
    }

    setIsSubmitting(true)
    setSubmitMessage(null)
    try {
      // Note: We are hardcoding user_id=1 for the demo until you have login
      const response = await fetch(`${API_BASE}/reviews`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: 1, 
          amenity_id: selectedAmenity.amenityId,
          overall_rating: userRating,
          rating_details: { submittedVia: 'web_client' },
        }),
      })

      if (!response.ok) {
        const detail = await response.text()
        throw new Error(detail || 'Request failed')
      }

      setSubmitMessage({ type: 'success', text: 'Thanks for sharing your rating!' })
      // Refresh data to show new average
      fetchAmenities(searchTerm)
    } catch (error) {
      setSubmitMessage({
        type: 'error',
        text: 'Unable to submit rating. You might have already reviewed this!',
      })
    } finally {
      setIsSubmitting(false)
    }
  }

  const interactiveStars = Array.from({ length: 5 }, (_, idx) => {
    const value = idx + 1
    const active = (hoverRating || userRating) >= value
    return (
      <button
        key={value}
        type="button"
        className={`star ${active ? 'active' : ''}`}
        onMouseEnter={() => setHoverRating(value)}
        onMouseLeave={() => setHoverRating(0)}
        onClick={() => setUserRating(value)}
        aria-label={`${value} star${value > 1 ? 's' : ''}`}
        aria-checked={userRating === value}
        role="radio"
      >
        ★
      </button>
    )
  })

  return (
    <main className="layout">
      <section className="sidebar">
        {/* Search Bar Integration */}
        <div className="search-container">
            <form onSubmit={handleSearch} className="search-form">
                <input 
                    type="text" 
                    placeholder="Search buildings..." 
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="search-input"
                />
                <button type="submit" className="search-button">
                    Search
                </button>
            </form>
            <button 
                onClick={() => setShowLeaderboard(true)}
                className="leaderboard-button"
            >
                🏆 Leaderboard
            </button>
        </div>

        {selectedAmenity ? (
          <div className="details">
            <p className="eyebrow">
              {titleCaseAmenity(selectedAmenity.type)} • Floor {selectedAmenity.floor}
            </p>
            <h1>{selectedAmenity.building?.name ?? 'Unknown Location'}</h1>
            <p className="address">{selectedAmenity.address?.address}</p>
            <p className="notes">{selectedAmenity.notes ?? 'Details coming soon.'}</p>

            <section className="rating-panel compact">
              <p className="eyebrow">Community rating</p>
              <div className="rating compact">
                <span className="score compact">
                  {selectedAmenity.review?.avgRating?.toFixed(1) ?? '—'}
                </span>
                <div>
                  <p className="stars compact">
                    {starDisplay(selectedAmenity.review?.avgRating)}
                  </p>
                  <p className="count compact">
                    {(selectedAmenity.review?.reviewCount ?? 0).toLocaleString()} reviews
                  </p>
                </div>
              </div>

              <div className="rating-form">
                <p className="eyebrow">Leave your rating</p>
                <div className="star-input" role="radiogroup" aria-label="Rate this amenity">
                  {interactiveStars}
                </div>
                <button
                  type="button"
                  onClick={handleRatingSubmit}
                  disabled={isSubmitting}
                >
                  {isSubmitting ? 'Submitting…' : 'Submit rating'}
                </button>
                {submitMessage && (
                  <p className={`submit-feedback ${submitMessage.type}`}>
                    {submitMessage.text}
                  </p>
                )}
                <button
                  type="button"
                  onClick={() => setShowExtras(true)}
                  className="extras-button"
                >
                  Extras
                </button>
              </div>
            </section>
          </div>
        ) : (
          <div className="details placeholder">
            <h1>Select an amenity</h1>
            <p className="notes">
              Tap any location pin on the map to view details, current feedback, and
              leave your own rating.
            </p>
          </div>
        )}
      </section>

      <section className="map-panel">
        <div ref={mapNodeRef} id="map" role="presentation" />
        <div className="map-legend">
          <p className="eyebrow">Legend</p>
          <ul>
            <li><span className="dot dot-water"></span> Water Fountain</li>
            <li><span className="dot dot-bathroom"></span> Bathroom</li>
            <li><span className="dot dot-vending"></span> Vending Machine</li>
          </ul>
        </div>
      </section>

      {/* Leaderboard Popup */}
      {showLeaderboard && (
        <div className="leaderboard-overlay" onClick={() => setShowLeaderboard(false)}>
          <div className="leaderboard-popup" onClick={(e) => e.stopPropagation()}>
            <div className="leaderboard-header">
              <h2>🏆 Leaderboards</h2>
              <button 
                className="close-button"
                onClick={() => setShowLeaderboard(false)}
                aria-label="Close leaderboard"
              >
                ×
              </button>
            </div>
            
            <div className="leaderboard-tabs">
              <button
                className={`tab ${activeTab === 'clean-bathrooms' ? 'active' : ''}`}
                onClick={() => setActiveTab('clean-bathrooms')}
              >
                Clean Bathrooms + Vending
              </button>
              <button
                className={`tab ${activeTab === 'coldest-fountains' ? 'active' : ''}`}
                onClick={() => setActiveTab('coldest-fountains')}
              >
                Coldest Fountains
              </button>
              <button
                className={`tab ${activeTab === 'overall' ? 'active' : ''}`}
                onClick={() => setActiveTab('overall')}
              >
                Overall Top Amenities
              </button>
            </div>

            <div className="leaderboard-content">
              {loadingLeaderboard ? (
                <div className="loading">Loading...</div>
              ) : (
                <div className="leaderboard-list">
                  {leaderboardData[activeTab].length === 0 ? (
                    <p className="empty-message">No data available</p>
                  ) : (
                    leaderboardData[activeTab].map((item, idx) => (
                      <div key={idx} className="leaderboard-item">
                        <div className="rank">#{idx + 1}</div>
                        <div className="item-details">
                          <h3>{item.building_name || 'Unknown Building'}</h3>
                          {activeTab === 'clean-bathrooms' && (
                            <>
                              <p className="item-meta">Floor: {item.amenity_type || 'N/A'}</p>
                              <p className="item-rating">
                                Rating: <strong>{item.avg_bathroom_rating || 'N/A'}</strong>
                              </p>
                              <p className="item-address">{item.address}</p>
                            </>
                          )}
                          {activeTab === 'coldest-fountains' && (
                            <>
                              <p className="item-meta">Floor: {item.floor || 'N/A'}</p>
                              <p className="item-rating">
                                Rating: <strong>{item.avg_rating || 'N/A'}</strong> | 
                                Cold Tags: <strong>{item.cold_tag_count || 0}</strong>
                              </p>
                              {item.notes && <p className="item-notes">{item.notes}</p>}
                            </>
                          )}
                          {activeTab === 'overall' && (
                            <>
                              <p className="item-meta">
                                {titleCaseAmenity(item.type || '')} • Floor {item.floor || 'N/A'}
                              </p>
                              <p className="item-rating">
                                Rating: <strong>{item.avg_rating || 'N/A'}</strong> | 
                                Reviews: <strong>{item.review_count || 0}</strong>
                              </p>
                            </>
                          )}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Extras Popup */}
      {showExtras && (
        <div className="leaderboard-overlay" onClick={() => setShowExtras(false)}>
          <div className="leaderboard-popup extras-popup" onClick={(e) => e.stopPropagation()}>
            <div className="leaderboard-header">
              <h2>⚙️ Extras - CRUD Operations</h2>
              <button 
                className="close-button"
                onClick={() => {
                  setShowExtras(false)
                  setExtrasMessage(null)
                }}
                aria-label="Close extras"
              >
                ×
              </button>
            </div>
            
            <div className="leaderboard-tabs">
              <button
                className={`tab ${activeExtraSection === 'building' ? 'active' : ''}`}
                onClick={() => setActiveExtraSection('building')}
              >
                Building
              </button>
              <button
                className={`tab ${activeExtraSection === 'amenity' ? 'active' : ''}`}
                onClick={() => setActiveExtraSection('amenity')}
              >
                Amenity
              </button>
              <button
                className={`tab ${activeExtraSection === 'tag' ? 'active' : ''}`}
                onClick={() => setActiveExtraSection('tag')}
              >
                Tag
              </button>
            </div>

            <div className="leaderboard-content extras-content">
              {extrasMessage && (
                <p className={`submit-feedback ${extrasMessage.type}`}>
                  {extrasMessage.text}
                </p>
              )}

              {/* Building Section */}
              {activeExtraSection === 'building' && (
                <div className="extras-section">
                  <h3>Create Building</h3>
                  <form onSubmit={handleCreateBuilding} className="extras-form">
                    <input
                      type="text"
                      placeholder="Building Name"
                      value={buildingForm.name}
                      onChange={(e) => setBuildingForm({ ...buildingForm, name: e.target.value })}
                      required
                    />
                    <input
                      type="text"
                      placeholder="Address"
                      value={buildingForm.address}
                      onChange={(e) => setBuildingForm({ ...buildingForm, address: e.target.value })}
                      required
                    />
                    <input
                      type="number"
                      step="any"
                      placeholder="Latitude"
                      value={buildingForm.lat}
                      onChange={(e) => setBuildingForm({ ...buildingForm, lat: e.target.value })}
                      required
                    />
                    <input
                      type="number"
                      step="any"
                      placeholder="Longitude"
                      value={buildingForm.lon}
                      onChange={(e) => setBuildingForm({ ...buildingForm, lon: e.target.value })}
                      required
                    />
                    <button type="submit">Create Building</button>
                  </form>

                  <h3>Update Building</h3>
                  <form onSubmit={handleUpdateBuilding} className="extras-form">
                    <input
                      type="number"
                      placeholder="Building ID"
                      value={updateForm.building.id}
                      onChange={(e) => setUpdateForm({ ...updateForm, building: { ...updateForm.building, id: e.target.value } })}
                      required
                    />
                    <input
                      type="text"
                      placeholder="New Name (optional)"
                      value={updateForm.building.name}
                      onChange={(e) => setUpdateForm({ ...updateForm, building: { ...updateForm.building, name: e.target.value } })}
                    />
                    <input
                      type="number"
                      placeholder="New Address ID (optional)"
                      value={updateForm.building.address_id}
                      onChange={(e) => setUpdateForm({ ...updateForm, building: { ...updateForm.building, address_id: e.target.value } })}
                    />
                    <button type="submit">Update Building</button>
                  </form>

                  <h3>Delete Building</h3>
                  <form onSubmit={handleDeleteBuilding} className="extras-form">
                    <input
                      type="number"
                      placeholder="Building ID"
                      value={deleteId.building}
                      onChange={(e) => setDeleteId({ ...deleteId, building: e.target.value })}
                      required
                    />
                    <button type="submit" className="delete-button">Delete Building</button>
                  </form>
                </div>
              )}

              {/* Amenity Section */}
              {activeExtraSection === 'amenity' && (
                <div className="extras-section">
                  <h3>Create Amenity</h3>
                  <form onSubmit={handleCreateAmenity} className="extras-form">
                    <input
                      type="number"
                      placeholder="Building ID"
                      value={amenityForm.building_id}
                      onChange={(e) => setAmenityForm({ ...amenityForm, building_id: e.target.value })}
                      required
                    />
                    <select
                      value={amenityForm.type}
                      onChange={(e) => setAmenityForm({ ...amenityForm, type: e.target.value })}
                      required
                    >
                      <option value="">Select Type</option>
                      <option value="Bathroom">Bathroom</option>
                      <option value="WaterFountain">Water Fountain</option>
                      <option value="VendingMachine">Vending Machine</option>
                    </select>
                    <input
                      type="text"
                      placeholder="Floor"
                      value={amenityForm.floor}
                      onChange={(e) => setAmenityForm({ ...amenityForm, floor: e.target.value })}
                      required
                    />
                    <input
                      type="text"
                      placeholder="Notes (optional)"
                      value={amenityForm.notes}
                      onChange={(e) => setAmenityForm({ ...amenityForm, notes: e.target.value })}
                    />
                    <button type="submit">Create Amenity</button>
                  </form>

                  <h3>Update Amenity</h3>
                  <form onSubmit={handleUpdateAmenity} className="extras-form">
                    <input
                      type="number"
                      placeholder="Amenity ID"
                      value={updateForm.amenity.id}
                      onChange={(e) => setUpdateForm({ ...updateForm, amenity: { ...updateForm.amenity, id: e.target.value } })}
                      required
                    />
                    <input
                      type="number"
                      placeholder="New Building ID (optional)"
                      value={updateForm.amenity.building_id}
                      onChange={(e) => setUpdateForm({ ...updateForm, amenity: { ...updateForm.amenity, building_id: e.target.value } })}
                    />
                    <select
                      value={updateForm.amenity.type}
                      onChange={(e) => setUpdateForm({ ...updateForm, amenity: { ...updateForm.amenity, type: e.target.value } })}
                    >
                      <option value="">Select Type (optional)</option>
                      <option value="Bathroom">Bathroom</option>
                      <option value="WaterFountain">Water Fountain</option>
                      <option value="VendingMachine">Vending Machine</option>
                    </select>
                    <input
                      type="text"
                      placeholder="New Floor (optional)"
                      value={updateForm.amenity.floor}
                      onChange={(e) => setUpdateForm({ ...updateForm, amenity: { ...updateForm.amenity, floor: e.target.value } })}
                    />
                    <input
                      type="text"
                      placeholder="New Notes (optional)"
                      value={updateForm.amenity.notes}
                      onChange={(e) => setUpdateForm({ ...updateForm, amenity: { ...updateForm.amenity, notes: e.target.value } })}
                    />
                    <button type="submit">Update Amenity</button>
                  </form>

                  <h3>Delete Amenity</h3>
                  <form onSubmit={handleDeleteAmenity} className="extras-form">
                    <input
                      type="number"
                      placeholder="Amenity ID"
                      value={deleteId.amenity}
                      onChange={(e) => setDeleteId({ ...deleteId, amenity: e.target.value })}
                      required
                    />
                    <button type="submit" className="delete-button">Delete Amenity</button>
                  </form>
                </div>
              )}

              {/* Tag Section */}
              {activeExtraSection === 'tag' && (
                <div className="extras-section">
                  <h3>Create Tag</h3>
                  <form onSubmit={handleCreateTag} className="extras-form">
                    <input
                      type="text"
                      placeholder="Tag Label"
                      value={tagForm.label}
                      onChange={(e) => setTagForm({ label: e.target.value })}
                      required
                    />
                    <button type="submit">Create Tag</button>
                  </form>

                  <h3>Update Tag</h3>
                  <form onSubmit={handleUpdateTag} className="extras-form">
                    <input
                      type="number"
                      placeholder="Tag ID"
                      value={updateForm.tag.id}
                      onChange={(e) => setUpdateForm({ ...updateForm, tag: { ...updateForm.tag, id: e.target.value } })}
                      required
                    />
                    <input
                      type="text"
                      placeholder="New Label"
                      value={updateForm.tag.label}
                      onChange={(e) => setUpdateForm({ ...updateForm, tag: { ...updateForm.tag, label: e.target.value } })}
                      required
                    />
                    <button type="submit">Update Tag</button>
                  </form>

                  <h3>Delete Tag</h3>
                  <form onSubmit={handleDeleteTag} className="extras-form">
                    <input
                      type="number"
                      placeholder="Tag ID"
                      value={deleteId.tag}
                      onChange={(e) => setDeleteId({ ...deleteId, tag: e.target.value })}
                      required
                    />
                    <button type="submit" className="delete-button">Delete Tag</button>
                  </form>
                </div>
              )}

            </div>
          </div>
        </div>
      )}
    </main>
  )
}