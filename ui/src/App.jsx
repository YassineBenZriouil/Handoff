import { useState, useEffect, useRef } from 'react'
import HandOverlay from './HandOverlay'
import './App.css'

const GESTURE_LABELS = {
  CLICK:       '🤏 Click',
  SWIPE_LEFT:  '👈 Swipe Left',
  SWIPE_RIGHT: '👉 Swipe Right',
  ZOOM_IN:     '🔍 Zoom In',
  ZOOM_OUT:    '🔎 Zoom Out',
}

export default function App() {
  const [connected, setConnected] = useState(false)
  const [gesture, setGesture]     = useState(null)
  const [landmarks, setLandmarks] = useState([])
  const [paused, setPaused]       = useState(false)
  const [flash, setFlash]         = useState(null)
  const [frameSrc, setFrameSrc]   = useState(null)
  const wsRef      = useRef(null)
  const flashTimer = useRef(null)

  useEffect(() => {
    function connect() {
      const ws = new WebSocket('ws://localhost:8765')
      wsRef.current = ws

      ws.onopen  = () => { console.log('[WS] connected'); setConnected(true) }
      ws.onclose = (e) => { console.warn('[WS] closed', e.code, e.reason); setConnected(false); setTimeout(connect, 2000) }
      ws.onerror = (e) => { console.error('[WS] error', e) }
      ws.onmessage = (e) => {
        let data
        try {
          data = JSON.parse(e.data)
        } catch (err) {
          console.error('[WS] JSON parse failed', err, e.data?.slice?.(0, 100))
          return
        }

        const keys = Object.keys(data)
        console.log('[WS] msg keys:', keys, '| frame?', !!data.frame, '| gesture:', data.gesture)

        const g = data.gesture
        if (data.frame) {
          console.log('[WS] frame received, length:', data.frame.length)
          setFrameSrc(`data:image/jpeg;base64,${data.frame}`)
        } else {
          console.warn('[WS] no frame in message')
        }
        setGesture(g || null)
        setLandmarks(data.landmarks || [])
        if (data.paused !== undefined) setPaused(data.paused)

        if (g && g !== 'MOVE' && GESTURE_LABELS[g]) {
          clearTimeout(flashTimer.current)
          setFlash(g)
          flashTimer.current = setTimeout(() => setFlash(null), 900)
        }
      }
    }
    connect()
    return () => wsRef.current?.close()
  }, [])

  function togglePause() {
    const ws = wsRef.current
    if (!ws || ws.readyState !== WebSocket.OPEN) return
    const next = !paused
    ws.send(JSON.stringify({ cmd: next ? 'pause' : 'resume' }))
    setPaused(next)
  }

  return (
    <div className="app">
      <header>
        <h1>HandOff</h1>
        <div className="header-right">
          <span className={`status ${connected ? 'on' : 'off'}`}>
            {connected ? 'Connected' : 'Disconnected'}
          </span>
          <button
            className={`toggle-btn ${paused ? 'paused' : 'active'}`}
            onClick={togglePause}
            disabled={!connected}
          >
            {paused ? '▶ Resume' : '⏸ Pause'}
          </button>
        </div>
      </header>

      <div className="camera-wrap">
        {frameSrc
          ? <img src={frameSrc} className="camera-feed" alt="camera" />
          : <div className="camera-waiting">Waiting for engine…</div>
        }
        <HandOverlay landmarks={landmarks} />

        {flash && (
          <div className="gesture-flash" key={flash + Date.now()}>
            {GESTURE_LABELS[flash]}
          </div>
        )}

        {paused && <div className="paused-overlay">PAUSED</div>}
      </div>

      <div className="gesture-bar">
        <span className="gesture-current">
          {gesture ? (GESTURE_LABELS[gesture] ?? gesture) : '—'}
        </span>
        <span className="landmarks-count">
          {landmarks.length ? `${landmarks.length} landmarks` : 'No hand'}
        </span>
      </div>
    </div>
  )
}
