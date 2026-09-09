import { useEffect } from 'react'

import { useLocalSetting } from '@/hooks/useLocalSetting'

export type Theme = 'light' | 'dark'

/**
 * The portal_fe tokens ship a `.dark` variant, so switching themes is a class
 * on <html> rather than a second stylesheet.
 */
export function useTheme() {
  const [theme, setTheme] = useLocalSetting<Theme>('theme', 'light')

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark')
  }, [theme])

  return { theme, setTheme }
}
