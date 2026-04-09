import { BrowserRouter, Routes, Route } from 'react-router'

function Home() {
  return (
    <div className="min-h-screen bg-primary text-text-primary font-mono flex items-center justify-center">
      <div className="text-center">
        <h1 className="text-[38px] font-bold mb-4">helPRs</h1>
        <p className="text-text-secondary text-[16px]">
          Socratic comprehension sessions for pull requests
        </p>
      </div>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
      </Routes>
    </BrowserRouter>
  )
}
