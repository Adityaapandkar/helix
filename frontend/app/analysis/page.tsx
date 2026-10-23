"use client"

import { useEffect, useState } from "react"
import { useSearchParams } from "next/navigation"
import { Canvas } from "@react-three/fiber"
import { Environment, OrbitControls } from "@react-three/drei"
import Link from "next/link"
import { Progress } from "@/components/ui/progress"
import ProteinModel from "@/components/protein-model"

export default function AnalysisPage() {
  const searchParams = useSearchParams()
  const proteinId = searchParams.get("id") || "P68871"
  const proteinName = "Hemoglobin"

  const [currentStep, setCurrentStep] = useState(1)
  const [progress, setProgress] = useState(0)
  const [timeElapsed, setTimeElapsed] = useState(0)

  useEffect(() => {
    const interval = setInterval(() => {
      if (currentStep < 4) {
        if (progress >= 100) {
          setCurrentStep((prev) => prev + 1)
          setProgress(0)
        } else {
          setProgress((prev) => Math.min(prev + 2, 100))
        }
      }

      setTimeElapsed((prev) => prev + 1)
    }, 1000)

    return () => clearInterval(interval)
  }, [currentStep, progress])

  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${mins}m ${secs}s`
  }

  return (
    <div className="relative min-h-screen overflow-hidden bg-gradient-to-b from-slate-950 via-indigo-950 to-purple-950">
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
          <Link
            href="/"
            className="flex items-center gap-2 rounded-md border border-slate-700 bg-slate-800/50 px-3 py-1.5 text-sm text-slate-300 transition-colors hover:bg-slate-800 hover:text-white"
          >
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
            >
              <path d="m12 19-7-7 7-7" />
              <path d="M19 12H5" />
            </svg>
            Back to Home
          </Link>
        </div>
      </header>

      {/* Content */}
      <div className="container py-8">
        <h1 className="mb-2 text-3xl font-bold text-white">Analysis Progress</h1>
        <p className="mb-8 text-slate-300">
          Analyzing protein {proteinId} ({proteinName})
        </p>

        <div className="grid gap-8 lg:grid-cols-5">
          {/* Left Column - Progress Steps */}
          <div className="lg:col-span-2">
            <div className="relative">
              {/* Vertical Line */}
              <div className="absolute left-6 top-8 h-[calc(100%-4rem)] w-0.5 bg-gradient-to-b from-purple-500 via-indigo-500 to-slate-700"></div>

              {/* Step 1 */}
              <div className="mb-8">
                <div className="flex items-start gap-4">
                  <div
                    className={`relative flex h-12 w-12 shrink-0 items-center justify-center rounded-full ${
                      currentStep >= 1 ? "bg-purple-600 text-white" : "bg-slate-800 text-slate-400"
                    }`}
                  >
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
                    {currentStep === 1 && (
                      <div className="absolute -right-1 -top-1 h-3 w-3 animate-ping rounded-full bg-purple-400"></div>
                    )}
                  </div>
                  <div className="flex-1">
                    <div className="rounded-lg bg-slate-900/80 p-4 backdrop-blur-sm">
                      <h3 className="mb-2 text-lg font-semibold text-white">Sequence Analysis</h3>
                      <p className="mb-3 text-sm text-slate-300">Analyzing protein sequence and predicting domains</p>
                      {currentStep === 1 && (
                        <div className="space-y-2">
                          <div className="flex items-center gap-2">
                            <div className="h-2 w-2 animate-pulse rounded-full bg-green-500"></div>
                            <span className="text-xs text-green-400">Loading protein sequence data...</span>
                          </div>
                          <div className="flex items-center gap-2">
                            <div className="h-2 w-2 animate-pulse rounded-full bg-green-500"></div>
                            <span className="text-xs text-green-400">Identifying conserved domains...</span>
                          </div>
                          <div className="flex items-center gap-2">
                            <div className="h-2 w-2 animate-pulse rounded-full bg-green-500"></div>
                            <span className="text-xs text-green-400">Analyzing secondary structure...</span>
                          </div>
                          <Progress value={progress} className="mt-2 h-1.5" />
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </div>

              {/* Step 2 */}
              <div className="mb-8">
                <div className="flex items-start gap-4">
                  <div
                    className={`relative flex h-12 w-12 shrink-0 items-center justify-center rounded-full ${
                      currentStep >= 2 ? "bg-indigo-600 text-white" : "bg-slate-800 text-slate-400"
                    }`}
                  >
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
                      <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
                      <polyline points="3.29 7 12 12 20.71 7" />
                      <line x1="12" y1="22" x2="12" y2="12" />
                    </svg>
                    {currentStep === 2 && (
                      <div className="absolute -right-1 -top-1 h-3 w-3 animate-ping rounded-full bg-indigo-400"></div>
                    )}
                  </div>
                  <div className="flex-1">
                    <div className="rounded-lg bg-slate-900/80 p-4 backdrop-blur-sm">
                      <h3 className="mb-2 text-lg font-semibold text-white">Structure Prediction</h3>
                      <p className="text-sm text-slate-300">3D structure prediction using AI models</p>
                      {currentStep === 2 && <Progress value={progress} className="mt-2 h-1.5" />}
                    </div>
                  </div>
                </div>
              </div>

              {/* Step 3 */}
              <div className="mb-8">
                <div className="flex items-start gap-4">
                  <div
                    className={`relative flex h-12 w-12 shrink-0 items-center justify-center rounded-full ${
                      currentStep >= 3 ? "bg-blue-600 text-white" : "bg-slate-800 text-slate-400"
                    }`}
                  >
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
                      <circle cx="12" cy="12" r="3" />
                      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
                    </svg>
                    {currentStep === 3 && (
                      <div className="absolute -right-1 -top-1 h-3 w-3 animate-ping rounded-full bg-blue-400"></div>
                    )}
                  </div>
                  <div className="flex-1">
                    <div className="rounded-lg bg-slate-900/80 p-4 backdrop-blur-sm">
                      <h3 className="mb-2 text-lg font-semibold text-white">Binding Site Identification</h3>
                      <p className="text-sm text-slate-300">Detecting potential binding sites</p>
                      {currentStep === 3 && <Progress value={progress} className="mt-2 h-1.5" />}
                    </div>
                  </div>
                </div>
              </div>

              {/* Step 4 */}
              <div className="mb-8">
                <div className="flex items-start gap-4">
                  <div
                    className={`relative flex h-12 w-12 shrink-0 items-center justify-center rounded-full ${
                      currentStep >= 4 ? "bg-emerald-600 text-white" : "bg-slate-800 text-slate-400"
                    }`}
                  >
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
                      <circle cx="12" cy="12" r="10" />
                      <circle cx="12" cy="12" r="4" />
                      <line x1="4.93" y1="4.93" x2="9.17" y2="9.17" />
                      <line x1="14.83" y1="14.83" x2="19.07" y2="19.07" />
                      <line x1="14.83" y1="9.17" x2="19.07" y2="4.93" />
                      <line x1="4.93" y1="19.07" x2="9.17" y2="14.83" />
                    </svg>
                    {currentStep === 4 && (
                      <div className="absolute -right-1 -top-1 h-3 w-3 animate-ping rounded-full bg-emerald-400"></div>
                    )}
                  </div>
                  <div className="flex-1">
                    <div className="rounded-lg bg-slate-900/80 p-4 backdrop-blur-sm">
                      <h3 className="mb-2 text-lg font-semibold text-white">Molecule Design</h3>
                      <p className="text-sm text-slate-300">Designing potential drug molecules</p>
                      {currentStep === 4 && <Progress value={progress} className="mt-2 h-1.5" />}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Right Column - 3D Visualization */}
          <div className="lg:col-span-3">
            <div className="grid gap-6">
              {/* 3D Visualization */}
              <div className="relative overflow-hidden rounded-xl border border-slate-800 bg-slate-900/60 backdrop-blur-sm">
                <div className="h-[400px] w-full">
                  <Canvas camera={{ position: [0, 0, 15] }}>
                    <ambientLight intensity={0.5} />
                    <pointLight position={[10, 10, 10]} intensity={0.8} />
                    <ProteinModel position={[0, 0, 0]} scale={3} />
                    <Environment preset="city" />
                    <OrbitControls enableZoom={true} autoRotate autoRotateSpeed={0.5} />
                  </Canvas>
                </div>
                <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                  {currentStep < 2 && (
                    <div className="rounded-lg bg-slate-900/80 px-6 py-3 text-center backdrop-blur-sm">
                      <p className="text-lg font-medium text-white">3D Visualization will appear here</p>
                    </div>
                  )}
                </div>
              </div>

              {/* Analysis Details */}
              <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-6 backdrop-blur-sm">
                <h3 className="mb-4 text-xl font-semibold text-white">Analysis Details</h3>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="rounded-lg bg-slate-800/50 p-4">
                    <h4 className="mb-2 text-sm font-medium text-slate-400">Status</h4>
                    <div className="flex items-center gap-2">
                      <div className="h-2.5 w-2.5 animate-pulse rounded-full bg-purple-500"></div>
                      <p className="text-lg font-medium text-white">Processing</p>
                    </div>
                  </div>
                  <div className="rounded-lg bg-slate-800/50 p-4">
                    <h4 className="mb-2 text-sm font-medium text-slate-400">Time Elapsed</h4>
                    <p className="text-lg font-medium text-white">{formatTime(timeElapsed)}</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

