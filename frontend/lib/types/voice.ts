export interface Voice {
  id: string;
  name: string;
  minimax_voice_id: string;
  language: string;
  tags: string[];
  is_preset: boolean;
  sample_local_path: string | null;
  created_at: string;
}

export interface VoiceListResponse {
  items: Voice[];
  total: number;
}
