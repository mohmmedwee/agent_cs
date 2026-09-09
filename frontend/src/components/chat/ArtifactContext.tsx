import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

export type Artifact = {
  fileId: string
  name: string
  content?: string
}

type ArtifactContextValue = {
  artifact: Artifact | null
  openArtifact: (next: Artifact) => void
  closeArtifact: () => void
}

const ArtifactContext = createContext<ArtifactContextValue | null>(null)

export function ArtifactProvider({ children }: { children: ReactNode }) {
  const [artifact, setArtifact] = useState<Artifact | null>(null)

  const openArtifact = useCallback((next: Artifact) => {
    setArtifact(next)
  }, [])

  const closeArtifact = useCallback(() => {
    setArtifact(null)
  }, [])

  const value = useMemo(
    () => ({ artifact, openArtifact, closeArtifact }),
    [artifact, openArtifact, closeArtifact],
  )

  return <ArtifactContext.Provider value={value}>{children}</ArtifactContext.Provider>
}

export function useArtifact() {
  const value = useContext(ArtifactContext)
  if (!value) {
    throw new Error('useArtifact must be used inside ArtifactProvider')
  }
  return value
}
