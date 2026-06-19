// Tipos de la herramienta "Fotos de partido" (estilo de vídeo V2 / viral).

export interface MatchImageResult {
  url: string;
  thumbnail: string;
  title: string;
  width: number;
  height: number;
}

export interface MatchPhotoSearchRequest {
  query: string;
  limit?: number;
}

export interface MatchPhotoSearchResponse {
  images: MatchImageResult[];
}

export interface MatchPhotoFolder {
  name: string;
  count: number;
}

export interface MatchPhotoFoldersResponse {
  folders: MatchPhotoFolder[];
}

export interface MatchPhotoItem {
  filename: string;
  url: string;
  width: number;
  height: number;
  size_kb: number;
}

export interface MatchPhotoListResponse {
  team: string;
  photos: MatchPhotoItem[];
}

export interface MatchPhotoSaveRequest {
  image_url: string;
  team: string;
}

export interface MatchPhotoSaveResponse {
  team: string;
  filename: string;
  url: string;
}

export interface MatchTeamStatus {
  name: string;
  has_photos: boolean;
  count: number;
}

export interface MatchTeamsForDateResponse {
  date: string;
  teams: MatchTeamStatus[];
}

export interface MatchAutoFetchRequest {
  team: string;
  mode: "missing" | "all";
  query?: string;
}

export interface MatchAutoFetchResponse {
  team: string;
  status: "created" | "exists" | "no_good" | "failed";
  filename: string | null;
  url: string | null;
  source: string | null;
  query: string | null;
  count: number;
  reason: string | null;
}
