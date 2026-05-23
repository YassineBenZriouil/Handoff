// SVG skeleton overlaid on top of camera feed (fills container via CSS)
const CONNECTIONS = [
  [0,1],[1,2],[2,3],[3,4],
  [0,5],[5,6],[6,7],[7,8],
  [0,9],[9,10],[10,11],[11,12],
  [0,13],[13,14],[14,15],[15,16],
  [0,17],[17,18],[18,19],[19,20],
  [5,9],[9,13],[13,17],
]

export default function HandOverlay({ landmarks }) {
  if (!landmarks.length) return null

  return (
    <svg className="hand-svg" viewBox="0 0 1 1" preserveAspectRatio="none">
      {CONNECTIONS.map(([a, b], i) => (
        <line
          key={i}
          x1={landmarks[a].x} y1={landmarks[a].y}
          x2={landmarks[b].x} y2={landmarks[b].y}
          stroke="#4ade80"
          strokeWidth="0.004"
          strokeLinecap="round"
        />
      ))}
      {landmarks.map((p, i) => (
        <circle
          key={i}
          cx={p.x} cy={p.y}
          r={i === 8 || i === 4 ? 0.014 : 0.008}
          fill={i === 8 ? '#facc15' : i === 4 ? '#f87171' : '#fff'}
        />
      ))}
    </svg>
  )
}
