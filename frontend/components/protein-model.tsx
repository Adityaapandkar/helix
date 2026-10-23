"use client"

import { useRef, useState } from "react"
import { useFrame } from "@react-three/fiber"
import { Sphere, Torus, Cylinder } from "@react-three/drei"

export default function ProteinModel({ position = [0, 0, 0], scale = 1 }) {
  const groupRef = useRef()
  const [hovered, setHovered] = useState(false)

  useFrame((state, delta) => {
    if (groupRef.current) {
      groupRef.current.rotation.y += delta * 0.1
    }
  })

  return (
    <group
      ref={groupRef}
      position={position}
      scale={scale}
      onPointerOver={() => setHovered(true)}
      onPointerOut={() => setHovered(false)}
    >
      {/* Central structure */}
      <Sphere args={[1, 32, 32]} position={[0, 0, 0]}>
        <meshStandardMaterial color={hovered ? "#8b5cf6" : "#6d28d9"} metalness={0.3} roughness={0.4} />
      </Sphere>

      {/* Connecting structures */}
      <Cylinder args={[0.2, 0.2, 3, 16]} position={[1.5, 0, 0]} rotation={[0, 0, Math.PI / 2]}>
        <meshStandardMaterial color="#4f46e5" metalness={0.3} roughness={0.4} />
      </Cylinder>

      <Cylinder args={[0.2, 0.2, 3, 16]} position={[-1.5, 0, 0]} rotation={[0, 0, Math.PI / 2]}>
        <meshStandardMaterial color="#4f46e5" metalness={0.3} roughness={0.4} />
      </Cylinder>

      <Cylinder args={[0.2, 0.2, 3, 16]} position={[0, 1.5, 0]} rotation={[0, 0, 0]}>
        <meshStandardMaterial color="#4f46e5" metalness={0.3} roughness={0.4} />
      </Cylinder>

      <Cylinder args={[0.2, 0.2, 3, 16]} position={[0, -1.5, 0]} rotation={[0, 0, 0]}>
        <meshStandardMaterial color="#4f46e5" metalness={0.3} roughness={0.4} />
      </Cylinder>

      {/* Outer nodes */}
      <Sphere args={[0.6, 24, 24]} position={[3, 0, 0]}>
        <meshStandardMaterial color="#3b82f6" metalness={0.3} roughness={0.4} />
      </Sphere>

      <Sphere args={[0.6, 24, 24]} position={[-3, 0, 0]}>
        <meshStandardMaterial color="#3b82f6" metalness={0.3} roughness={0.4} />
      </Sphere>

      <Sphere args={[0.6, 24, 24]} position={[0, 3, 0]}>
        <meshStandardMaterial color="#3b82f6" metalness={0.3} roughness={0.4} />
      </Sphere>

      <Sphere args={[0.6, 24, 24]} position={[0, -3, 0]}>
        <meshStandardMaterial color="#3b82f6" metalness={0.3} roughness={0.4} />
      </Sphere>

      {/* Additional decorative elements */}
      <Torus args={[1.2, 0.1, 16, 32]} position={[0, 0, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <meshStandardMaterial
          color="#8b5cf6"
          metalness={0.5}
          roughness={0.3}
          emissive="#4c1d95"
          emissiveIntensity={0.2}
        />
      </Torus>

      <Torus args={[1.2, 0.1, 16, 32]} position={[0, 0, 0]} rotation={[0, Math.PI / 2, 0]}>
        <meshStandardMaterial
          color="#8b5cf6"
          metalness={0.5}
          roughness={0.3}
          emissive="#4c1d95"
          emissiveIntensity={0.2}
        />
      </Torus>
    </group>
  )
}

