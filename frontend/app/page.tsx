"use client"

import { useState } from "react"
import { Search } from "lucide-react"
import { Canvas } from "@react-three/fiber"
import { Environment, Float, OrbitControls } from "@react-three/drei"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import Link from "next/link"
import ProteinModel from "@/components/protein-model"

export default function HomePage() {
  const [searchQuery, setSearchQuery] = useState("")

  return (
    <div className="relative min-h-screen overflow-hidden bg-gradient-to-b from-slate-950 via-indigo-950 to-purple-950">
      {/* 3D Background */}
      <div className="absolute inset-0 z-0 opacity-30">
        <Canvas camera={{ position: [0, 0, 15] }}>
          <ambientLight intensity={0.5} />
          <pointLight position={[10, 10, 10]} intensity={0.8} />
          <Float speed={1.5} rotationIntensity={0.5} floatIntensity={0.5}>
            <ProteinModel position={[0, 0, 0]} scale={3} />
          </Float>
          <Environment preset="city" />
          <OrbitControls enableZoom={false} autoRotate autoRotateSpeed={0.5} />
        </Canvas>
      </div>

      {/* Content */}
      <div className="relative z-10">
        {/* Header */}
        <header className="border-b border-slate-800/60 backdrop-blur-sm">
          <div className="container flex items-center justify-between py-4">
            <Link href="/" className="flex items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-purple-600 text-white">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width="20"
                  height="20"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M12 2L4 8l8 6 8-6-8-6z" />
                  <path d="M4 16l8 6 8-6" />
                  <path d="M4 8v8" />
                  <path d="M20 8v8" />
                </svg>
              </div>
              <span className="text-xl font-bold text-white">Protein Analysis Platform</span>
            </Link>
            <nav className="flex items-center gap-6">
              <Link
                href="/analysis"
                className="flex items-center gap-2 text-slate-300 hover:text-white transition-colors"
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width="18"
                  height="18"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" />
                  <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
                </svg>
                Analysis
              </Link>
              <Link
                href="/discovery"
                className="flex items-center gap-2 text-slate-300 hover:text-white transition-colors"
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width="18"
                  height="18"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <circle cx="12" cy="12" r="10" />
                  <line x1="2" y1="12" x2="22" y2="12" />
                  <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
                </svg>
                Discovery
              </Link>
            </nav>
          </div>
        </header>

        {/* Hero Section */}
        <section className="container py-16 md:py-24">
          <div className="mx-auto max-w-4xl text-center">
            <div className="mb-6 flex justify-center">
              <div className="relative h-16 w-16">
                <div className="absolute inset-0 animate-ping rounded-full bg-purple-500 opacity-20"></div>
                <div className="relative flex h-16 w-16 items-center justify-center rounded-full bg-gradient-to-r from-purple-600 to-indigo-600 text-white">
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    width="32"
                    height="32"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <path d="M12 2L4 8l8 6 8-6-8-6z" />
                    <path d="M4 16l8 6 8-6" />
                    <path d="M4 8v8" />
                    <path d="M20 8v8" />
                  </svg>
                </div>
              </div>
            </div>
            <h1 className="mb-6 bg-gradient-to-r from-white to-slate-300 bg-clip-text text-5xl font-bold tracking-tight text-transparent md:text-6xl">
              Protein Analysis & Drug Discovery
            </h1>
            <p className="mb-10 text-lg text-slate-300 md:text-xl">
              Enter a UniProt ID to unlock advanced computational insights for protein analysis and drug discovery.
            </p>

            <div className="mx-auto max-w-md">
              <div className="relative">
                <div className="absolute inset-0 -z-10 rounded-lg bg-gradient-to-r from-purple-600 to-indigo-600 blur-lg opacity-70"></div>
                <div className="relative flex overflow-hidden rounded-lg bg-slate-900/80 backdrop-blur-sm">
                  <Input
                    type="text"
                    placeholder="Try P68871 or P01308"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="flex-1 border-0 bg-transparent text-white placeholder-slate-400 focus-visible:ring-0 focus-visible:ring-offset-0"
                  />
                  <Button variant="ghost" size="icon" className="h-10 w-10 text-slate-400" aria-label="Search">
                    <Search className="h-5 w-5" />
                  </Button>
                </div>
              </div>
              <p className="mt-2 text-sm text-slate-400">Example: P68871 (Hemoglobin), P01308 (Insulin)</p>
              <div className="mt-4">
                <Link
                  href={`/analysis?id=${searchQuery || "P68871"}`}
                  className="inline-flex items-center justify-center rounded-md bg-gradient-to-r from-purple-600 to-indigo-600 px-6 py-2.5 text-sm font-medium text-white shadow-lg shadow-purple-900/30 hover:from-purple-700 hover:to-indigo-700 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:ring-offset-2 focus:ring-offset-slate-900"
                >
                  Analyze
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className="ml-2"
                  >
                    <path d="M5 12h14" />
                    <path d="m12 5 7 7-7 7" />
                  </svg>
                </Link>
              </div>
            </div>
          </div>
        </section>

        {/* Features Section */}
        <section className="container pb-24">
          <div className="grid gap-8 md:grid-cols-3">
            {/* Feature 1 */}
            <div className="group relative overflow-hidden rounded-xl bg-gradient-to-b from-slate-900 to-slate-900/80 p-6 shadow-lg transition-all hover:shadow-purple-900/20">
              <div className="absolute inset-0 -z-10 bg-gradient-to-br from-purple-900/20 to-transparent opacity-0 transition-opacity group-hover:opacity-100"></div>
              <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-lg bg-purple-900/30 text-purple-400">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width="24"
                  height="24"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M12 2L4 8l8 6 8-6-8-6z" />
                  <path d="M4 16l8 6 8-6" />
                  <path d="M4 8v8" />
                  <path d="M20 8v8" />
                </svg>
              </div>
              <h3 className="mb-2 text-xl font-semibold text-white">Sequence Analysis</h3>
              <p className="text-slate-300">
                Advanced protein sequence analysis with domain prediction and feature detection.
              </p>
            </div>

            {/* Feature 2 */}
            <div className="group relative overflow-hidden rounded-xl bg-gradient-to-b from-slate-900 to-slate-900/80 p-6 shadow-lg transition-all hover:shadow-indigo-900/20">
              <div className="absolute inset-0 -z-10 bg-gradient-to-br from-indigo-900/20 to-transparent opacity-0 transition-opacity group-hover:opacity-100"></div>
              <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-lg bg-indigo-900/30 text-indigo-400">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width="24"
                  height="24"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
                  <polyline points="3.29 7 12 12 20.71 7" />
                  <line x1="12" y1="22" x2="12" y2="12" />
                </svg>
              </div>
              <h3 className="mb-2 text-xl font-semibold text-white">Structure Prediction</h3>
              <p className="text-slate-300">State-of-the-art 3D structure prediction and visualization tools.</p>
            </div>

            {/* Feature 3 */}
            <div className="group relative overflow-hidden rounded-xl bg-gradient-to-b from-slate-900 to-slate-900/80 p-6 shadow-lg transition-all hover:shadow-blue-900/20">
              <div className="absolute inset-0 -z-10 bg-gradient-to-br from-blue-900/20 to-transparent opacity-0 transition-opacity group-hover:opacity-100"></div>
              <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-lg bg-blue-900/30 text-blue-400">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width="24"
                  height="24"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <circle cx="12" cy="12" r="10" />
                  <circle cx="12" cy="12" r="4" />
                  <line x1="4.93" y1="4.93" x2="9.17" y2="9.17" />
                  <line x1="14.83" y1="14.83" x2="19.07" y2="19.07" />
                  <line x1="14.83" y1="9.17" x2="19.07" y2="4.93" />
                  <line x1="14.83" y1="9.17" x2="18.36" y2="5.64" />
                  <line x1="4.93" y1="19.07" x2="9.17" y2="14.83" />
                </svg>
              </div>
              <h3 className="mb-2 text-xl font-semibold text-white">Drug Discovery</h3>
              <p className="text-slate-300">Intelligent drug molecule design and binding site prediction.</p>
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}

