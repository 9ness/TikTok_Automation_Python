"""Tab 'Voces' — listado de presets MiniMax + voces clonadas + clonado nuevo."""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from src.tiktok_shop.api import minimax_clone
from src.tiktok_shop.config import resolve_shop_root
from src.tiktok_shop.models import VoiceClone
from src.tiktok_shop.repos import VoiceRepo


def render() -> None:
    repo = VoiceRepo()

    st.subheader("🗣️ Voces disponibles")
    with st.spinner("🗣️ Cargando presets MiniMax + voces clonadas…"):
        voices = repo.list_all(include_presets=True)

    for v in voices:
        with st.container(border=True):
            c1, c2, c3 = st.columns([2, 2, 1])
            with c1:
                tag = "🟢 Preset" if v.is_preset else "🟣 Clonada"
                st.markdown(f"**{v.name}** · {tag}")
                st.caption(f"`{v.minimax_voice_id}` · {v.language} · {', '.join(v.tags)}")
            with c2:
                if st.button("🔊 Probar", key=f"test_voice_{v.id}"):
                    _test_voice(v)
            with c3:
                if not v.is_preset:
                    if st.button("🗑️", key=f"del_voice_{v.id}"):
                        repo.delete(v.id)
                        st.rerun()

    st.divider()
    _render_clone_form(repo)


def _test_voice(v: VoiceClone) -> None:
    from src.locutor import generate_voice_sample

    out_dir = os.path.join(resolve_shop_root(), "_voice_samples")
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    out_path = os.path.join(out_dir, f"{v.minimax_voice_id}.mp3")
    try:
        generate_voice_sample(v.minimax_voice_id, out_path)
        st.audio(out_path)
    except Exception as e:
        st.error(f"No se pudo generar muestra: {e}")


def _render_clone_form(repo: VoiceRepo) -> None:
    st.subheader("➕ Clonar voz nueva")
    with st.form("shop_voice_clone_form"):
        name = st.text_input("Nombre", placeholder="Mi voz energética ES")
        language = st.selectbox("Idioma", ["es", "en", "pt", "fr", "it", "de"], index=0)
        tags_raw = st.text_input("Tags (coma-separados)", placeholder="energetic, male, young")
        sample = st.file_uploader("Sample MP3 (10-30s, voz limpia)", type=["mp3", "wav", "m4a"])
        manual_voice_id = st.text_input(
            "O voice_id directo (si ya lo clonaste por otro canal)",
            placeholder="custom_voice_xyz",
        )

        submitted = st.form_submit_button("💾 Guardar voz", type="primary")

    if submitted:
        if not name.strip():
            st.error("Nombre obligatorio.")
            return

        voice_id = manual_voice_id.strip() if manual_voice_id.strip() else None
        sample_path = None

        if not voice_id:
            if not sample:
                st.error("Sube un MP3 o introduce un voice_id manual.")
                return
            # Guardar sample
            samples_dir = os.path.join(
                resolve_shop_root(), "_voice_samples"
            )
            Path(samples_dir).mkdir(parents=True, exist_ok=True)
            sample_path = os.path.join(samples_dir, sample.name)
            with open(sample_path, "wb") as f:
                f.write(sample.getbuffer())

            if not minimax_clone.is_available():
                st.error("MiniMax no configurado. Define MINIMAX_API_KEY en .env.")
                return

            try:
                with st.spinner("☁️ Subiendo sample a MiniMax…"):
                    voice_id = minimax_clone.clone_voice(
                        sample_path,
                        name=name.strip(),
                        language=language,
                    )
            except Exception as e:
                st.error(f"Clonado falló: {e}")
                return

        v = VoiceClone(
            name=name.strip(),
            minimax_voice_id=voice_id,
            language=language,
            tags=[t.strip() for t in tags_raw.split(",") if t.strip()],
            is_preset=False,
            sample_local_path=sample_path,
        )
        repo.save(v)
        st.success(f"✅ Voz '{v.name}' guardada (voice_id: `{voice_id}`).")
        st.rerun()
