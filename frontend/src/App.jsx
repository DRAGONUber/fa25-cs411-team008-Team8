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

  // -- 1. Fetch Data from Backend (Search Integration) --
  const fetchAmenities = async (keyword = '') => {
    try {
      const url = new URL(`${API_BASE}/amenities?limit=200`)
      // If keyword exists, append it to URL
      if (keyword) url.searchParams.append('keyword', keyword)
      
      const res = await fetch(url)
      if (!res.ok) throw new Error('Failed to fetch')
      
      const data = await res.json()
      
      // Transform SQL flat response to UI structure
      const transformed = data.map(item => ({
        amenityId: item.amenityid,
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
        <div className="search-container" style={{ paddingBottom: '1rem' }}>
            <form onSubmit={handleSearch} style={{ display: 'flex', gap: '0.5rem' }}>
                <input 
                    type="text" 
                    placeholder="Search buildings..." 
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    style={{ flex: 1, padding: '0.5rem', borderRadius: '4px', border: '1px solid #ccc' }}
                />
                <button type="submit" style={{ padding: '0.5rem 1rem', background: '#0ea5e9', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}>
                    Search
                </button>
            </form>
        </div>

        {selectedAmenity ? (
          <div className="details">
            <p className="eyebrow">
              {titleCaseAmenity(selectedAmenity.type)} • Floor {selectedAmenity.floor}
            </p>
            <h1>{selectedAmenity.building?.name ?? 'Unknown Location'}</h1>
            <p className="address">{selectedAmenity.address?.address}</p>
            <p className="notes">{selectedAmenity.notes ?? 'Details coming soon.'}</p>

            <section className="rating-panel">
              <p className="eyebrow">Community rating</p>
              <div className="rating">
                <span className="score">
                  {selectedAmenity.review?.avgRating?.toFixed(1) ?? '—'}
                </span>
                <div>
                  <p className="stars">
                    {starDisplay(selectedAmenity.review?.avgRating)}
                  </p>
                  <p className="count">
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

        <section className="legend">
          <p className="eyebrow">Legend</p>
          <ul>
            <li><span className="dot dot-water"></span> Water Fountain</li>
            <li><span className="dot dot-bathroom"></span> Bathroom</li>
            <li><span className="dot dot-vending"></span> Vending Machine</li>
          </ul>
        </section>
      </section>

      <section className="map-panel">
        <div ref={mapNodeRef} id="map" role="presentation" />
      </section>
    </main>
  )
}