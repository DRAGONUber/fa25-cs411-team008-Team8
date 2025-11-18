import { useEffect, useMemo, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import './App.css'

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

const addressSeed = [
  {
    addressId: 1,
    address: 'Illini Union, 1401 W Green St, Urbana, IL 61801',
    lat: 40.109618,
    lon: -88.227219,
  },
  {
    addressId: 2,
    address: 'Siebel Center, 201 N Goodwin Ave, Urbana, IL 61801',
    lat: 40.113798,
    lon: -88.224983,
  },
  {
    addressId: 3,
    address: 'ECE Building, 306 N Wright St, Urbana, IL 61801',
    lat: 40.114585,
    lon: -88.226937,
  },
  {
    addressId: 4,
    address: 'Krannert Center, 500 S Goodwin Ave, Urbana, IL 61801',
    lat: 40.105021,
    lon: -88.221654,
  },
  {
    addressId: 5,
    address: 'Gregory Hall, 810 S Wright St, Champaign, IL 61820',
    lat: 40.108372,
    lon: -88.228782,
  },
]

const buildingSeed = [
  { buildingId: 1, name: 'Illini Union', addressId: 1 },
  { buildingId: 2, name: 'Siebel Center for CS', addressId: 2 },
  { buildingId: 3, name: 'ECE Building', addressId: 3 },
  { buildingId: 4, name: 'Krannert Center for the Performing Arts', addressId: 4 },
  { buildingId: 5, name: 'Gregory Hall', addressId: 5 },
]

const amenitySeed = [
  {
    amenityId: 1,
    buildingId: 1,
    type: 'WaterFountain',
    floor: '1',
    notes: 'Next to the information desk and seating area.',
  },
  {
    amenityId: 2,
    buildingId: 1,
    type: 'Bathroom',
    floor: '2',
    notes: 'Gender-inclusive restroom near the south staircase.',
  },
  {
    amenityId: 3,
    buildingId: 2,
    type: 'VendingMachine',
    floor: '1',
    notes: 'Snacks and drinks across from the ACM office.',
  },
  {
    amenityId: 4,
    buildingId: 2,
    type: 'WaterFountain',
    floor: '3',
    notes: 'Chilled bottle filler outside lab 3401.',
  },
  {
    amenityId: 5,
    buildingId: 3,
    type: 'Bathroom',
    floor: '1',
    notes: 'Accessible restroom near the west lobby.',
  },
  {
    amenityId: 6,
    buildingId: 3,
    type: 'VendingMachine',
    floor: '2',
    notes: 'Combo machine beside the graduate lounge.',
  },
  {
    amenityId: 7,
    buildingId: 4,
    type: 'WaterFountain',
    floor: 'Lobby',
    notes: 'Bottle filler behind the ticket counter.',
  },
  {
    amenityId: 8,
    buildingId: 4,
    type: 'Bathroom',
    floor: 'Lower Level',
    notes: 'Family restroom across from the studio theatre.',
  },
  {
    amenityId: 9,
    buildingId: 5,
    type: 'WaterFountain',
    floor: 'Basement',
    notes: 'Historic fountain near lecture hall 100.',
  },
  {
    amenityId: 10,
    buildingId: 5,
    type: 'VendingMachine',
    floor: '1',
    notes: 'Coffee and snack machine in the north hallway.',
  },
]

const reviewSeed = [
  { reviewId: 501, amenityId: 1, avgRating: 4.6, reviewCount: 2947 },
  { reviewId: 502, amenityId: 2, avgRating: 4.3, reviewCount: 1360 },
  { reviewId: 503, amenityId: 3, avgRating: 4.1, reviewCount: 982 },
  { reviewId: 504, amenityId: 4, avgRating: 4.9, reviewCount: 412 },
  { reviewId: 505, amenityId: 5, avgRating: 4.2, reviewCount: 1510 },
  { reviewId: 506, amenityId: 6, avgRating: 3.9, reviewCount: 688 },
  { reviewId: 507, amenityId: 7, avgRating: 4.8, reviewCount: 802 },
  { reviewId: 508, amenityId: 8, avgRating: 4.4, reviewCount: 590 },
  { reviewId: 509, amenityId: 9, avgRating: 4.7, reviewCount: 231 },
  { reviewId: 510, amenityId: 10, avgRating: 3.8, reviewCount: 450 },
]

const amenityColors = {
  WaterFountain: '#0ea5e9',
  Bathroom: '#8b5cf6',
  VendingMachine: '#f97316',
}

const titleCaseAmenity = (type) =>
  type
    .replace(/([A-Z])/g, ' $1')
    .trim()
    .replace(/^./, (char) => char.toUpperCase())

const starDisplay = (value = 0) => {
  const rounded = Math.round(value)
  return '★'.repeat(rounded).padEnd(5, '☆')
}

export default function App() {
  const mapNodeRef = useRef(null)
  const [userRating, setUserRating] = useState(0)
  const [hoverRating, setHoverRating] = useState(0)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [submitMessage, setSubmitMessage] = useState(null)

  const addressById = useMemo(
    () => new Map(addressSeed.map((entry) => [entry.addressId, entry])),
    [],
  )
  const buildingById = useMemo(
    () => new Map(buildingSeed.map((entry) => [entry.buildingId, entry])),
    [],
  )
  const reviewByAmenity = useMemo(
    () => new Map(reviewSeed.map((entry) => [entry.amenityId, entry])),
    [],
  )

  const enrichedAmenities = useMemo(
    () =>
      amenitySeed.map((amenity) => {
        const building = buildingById.get(amenity.buildingId)
        const address = building ? addressById.get(building.addressId) : undefined
        const review = reviewByAmenity.get(amenity.amenityId)
        return { ...amenity, building, address, review }
      }),
    [addressById, buildingById, reviewByAmenity],
  )

  const [selectedAmenity, setSelectedAmenity] = useState(
    enrichedAmenities[0] ?? null,
  )

  useEffect(() => {
    if (!mapNodeRef.current) return () => {}

    const map = L.map(mapNodeRef.current, {
      scrollWheelZoom: true,
      zoomControl: true,
    }).setView([40.1096, -88.2273], 14.5)

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map)

    enrichedAmenities.forEach((amenity) => {
      const { address, building } = amenity
      if (!address || !building) return
      const color = amenityColors[amenity.type] ?? '#0f172a'

      const marker = L.circleMarker([address.lat, address.lon], {
        radius: 11,
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
          <p>${amenity.notes ?? 'Details coming soon.'}</p>
        </article>`
      )
    })

    return () => {
      map.remove()
    }
  }, [enrichedAmenities])

  const handleRatingSubmit = async () => {
    if (!selectedAmenity?.review?.reviewId) {
      setSubmitMessage({ type: 'error', text: 'No review slot available.' })
      return
    }
    if (userRating === 0) {
      setSubmitMessage({ type: 'error', text: 'Pick a star rating first.' })
      return
    }

    setIsSubmitting(true)
    setSubmitMessage(null)
    try {
      const response = await fetch(
        `${API_BASE}/reviews/${selectedAmenity.review.reviewId}`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            overall_rating: userRating,
            rating_details: {
              submittedVia: 'prototype',
              amenityId: selectedAmenity.amenityId,
            },
          }),
        },
      )

      if (!response.ok) {
        const detail = await response.text()
        throw new Error(detail || 'Request failed')
      }

      setSubmitMessage({ type: 'success', text: 'Thanks for sharing your rating!' })
    } catch (error) {
      setSubmitMessage({
        type: 'error',
        text: 'Unable to submit rating right now. Please try again later.',
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
            <li>
              <span className="dot dot-water" aria-hidden="true"></span>
              Water Fountain
            </li>
            <li>
              <span className="dot dot-bathroom" aria-hidden="true"></span>
              Bathroom
            </li>
            <li>
              <span className="dot dot-vending" aria-hidden="true"></span>
              Vending Machine
            </li>
          </ul>
        </section>
      </section>

      <section className="map-panel">
        <div ref={mapNodeRef} id="map" role="presentation" />
      </section>
    </main>
  )
}
