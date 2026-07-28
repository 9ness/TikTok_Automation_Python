// Espejo de `src/api/schemas/nicho_pov_bof/models.py`.

export interface SourceInfo {
  slug: string;
  label: string;
}

export interface SourcesListResponse {
  items: SourceInfo[];
}

export interface ProductFolder {
  name: string;
  id: string;
  completed: boolean;
}

export interface FoldersListResponse {
  source: string;
  items: ProductFolder[];
  total: number;
  completed_count: number;
  /** Primera carpeta sin completar — lo que la UI muestra por defecto. */
  current: string | null;
}

export interface PhotoInfo {
  id: string;
  name: string;
  size: number;
  mime: string;
}

export interface PhotosListResponse {
  source: string;
  folder: string;
  items: PhotoInfo[];
}

export interface BackupCheckResponse {
  last_snapshot: string | null;
  has_changes: boolean;
  would_be_full: boolean;
  full_copy_ratio: number;
  n_added: number;
  n_modified: number;
  n_deleted: number;
  n_total_source: number;
  change_ratio: number;
}

export interface BackupSyncResponse {
  job_id: string;
  title: string;
  position_in_queue: number;
}

export interface MarkCompletedRequest {
  source: string;
  folder: string;
  completed: boolean;
}

export interface MarkCompletedResponse {
  source: string;
  folder: string;
  completed: boolean;
  completed_count: number;
  total: number;
  next_folder: string | null;
}
