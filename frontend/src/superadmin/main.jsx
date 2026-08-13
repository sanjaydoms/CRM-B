import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import SuperAdmin from './SuperAdmin.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <SuperAdmin />
  </StrictMode>,
)
