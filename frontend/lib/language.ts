/** Tablas de idioma para TikTok Shop. Centralizadas para que UI +
 *  generador usen los mismos códigos sin divergir. */

export const LANGUAGE_OPTIONS = [
  { code: "es_ES", label: "🇪🇸 Español (España)", short: "ES España" },
  { code: "es_LATAM", label: "🌎 Español (Latam)", short: "ES Latam" },
  { code: "en_US", label: "🇺🇸 English (US)", short: "EN US" },
  { code: "en_UK", label: "🇬🇧 English (UK)", short: "EN UK" },
  { code: "pt_BR", label: "🇧🇷 Português (Brasil)", short: "PT BR" },
  { code: "fr_FR", label: "🇫🇷 Français (France)", short: "FR" },
] as const;

export type LanguageCode = (typeof LANGUAGE_OPTIONS)[number]["code"];

/** Voz MiniMax preset default para cada idioma. Se aplica como fallback
 *  al aplicar un preset al form de Auto vídeo si el preset no especifica
 *  voice_id. Lo que el user puede sobrescribir con clones. */
export const DEFAULT_VOICE_BY_LANGUAGE: Record<string, string> = {
  es_ES: "Spanish_EnergeticBoy",         // latino aceptable hasta que clones España
  es_LATAM: "Spanish_EnergeticBoy",
  en_US: "English_EnergeticBoy",
  en_UK: "English_EnergeticBoy",
  pt_BR: "Spanish_EnergeticBoy",         // MiniMax no tiene PT preset estable
  fr_FR: "English_EnergeticBoy",         // fallback inglés hasta tener clones FR
};

/** Devuelve el label corto para mostrar en badges/header. */
export function languageShort(code: string | undefined | null): string {
  const found = LANGUAGE_OPTIONS.find((o) => o.code === code);
  return found?.short ?? "ES España";
}

/** Voz default para el idioma del producto. Si idioma no reconocido →
 *  Spanish_EnergeticBoy (fallback histórico). */
export function defaultVoiceForLanguage(code: string | undefined | null): string {
  if (!code) return "Spanish_EnergeticBoy";
  return DEFAULT_VOICE_BY_LANGUAGE[code] ?? "Spanish_EnergeticBoy";
}
