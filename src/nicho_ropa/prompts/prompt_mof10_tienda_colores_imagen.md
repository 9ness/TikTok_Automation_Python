<!-- "TIENDA COLORES · 15 SEGUNDOS EN DOS CLIPS" (MUJER), paso 1 de 3: la
     IMAGEN, en Flow con la foto de la prenda como referencia.

     NO es un formato del curso: sale de cinco vídeos virales de pantalones de
     mujer (sep 2026) que comparten la misma receta —una chica en una tienda
     de ropa con top blanco ajustado, cuerpo entero de frente, el pantalón
     puesto; arranca nombrando tres o cuatro colores y en cada color el
     pantalón cambia de golpe (es un corte de edición, no una toma nueva);
     luego enseña la cintura y los bolsillos, se da la vuelta, se agacha y
     cierra con "varios colores en tienda".

     Esta imagen es el PRIMER fotograma del clip 1 (de frente). Los cortes de
     color NO se generan en Flow: al montar, la app recolorea este mismo
     fotograma con Gemini y los intercala al ritmo de las palabras. Por eso la
     pose tiene que ser frontal y el pantalón verse entero (cada color usa el
     fotograma del instante en que lo nombra, con la pose que tenga).

     La segunda imagen (`prompt_mof10_tienda_colores_imagen2.md`) es la misma
     chica de espaldas, en la misma tienda: es el arranque del clip 2. -->

{
  "subject": {
    "description": "A completely random adult woman standing still and facing the camera inside a real clothing store, looking directly at the camera. Her identity, face, body, hair, skin tone, age and overall appearance must be entirely random in every generation. She is being recorded in a casual UGC style with a smartphone by another person. Her full body must be visible from head to toe, standing straight, weight on both feet, in a relaxed and natural posture.",
    "appearance": "entirely random",
    "age": "random adult age between 20 and 32",
    "expression": "natural, confident, slight smile, as if about to start talking",
    "gaze": "direct eye contact with the camera",
    "head_orientation": "naturally facing the camera",
    "hair": "completely random hair type, length, color and style, worn loose or in a ponytail",
    "body_type": "completely random body type",
    "skin_tone": "completely random natural skin tone"
  },
  "clothing": {
    "source": "The female subject MUST wear exactly the garment shown in the provided reference image.",
    "instructions": [
      "Use the provided reference image exclusively as the garment reference.",
      "The female subject MUST wear the exact garment shown in the reference image, in the exact same color.",
      "Replicate every detail with maximum accuracy: color, fabric, texture, seams, pleats, waistband, drawstring, buttons, pockets, fit, cut, length and proportion.",
      "Do not reinterpret, redesign, replace, simplify, recolor, add or omit any part of the referenced garment.",
      "The referenced garment must remain exactly the same and must be the main visual focus, fully visible from the waistband to the hem.",
      "On top she wears a plain, fitted, PLAIN WHITE top with no print, no logo and no text: a fitted white t-shirt or a fitted white long-sleeve top, cropped or tucked in so the waistband of the referenced garment is fully visible.",
      "Shoes: simple and neutral (white or light grey sneakers, or plain sandals or flats), chosen to match the garment; never shoes that draw attention.",
      "No jacket, coat, bag, belt or any garment that covers or overlaps the referenced garment, unless a belt is part of the reference image.",
      "The complete outfit must look clean, simple and coordinated: the garment is the star and the white top is a neutral canvas.",
      "The garment is the only fixed visual element. The woman and the store must be completely different and random in every generation."
    ]
  },
  "face": {
    "instructions": "Generate a completely random adult female face. Do not follow, reproduce or imitate any specific facial identity, facial description or predefined appearance.",
    "skin_texture": "completely random natural and realistic skin texture, with visible pores and no excessive retouching",
    "makeup": "light natural makeup or no makeup"
  },
  "accessories": {
    "instructions": "Preserve any accessories visible in the reference image. Otherwise at most small, discreet accessories (thin bracelets, small earrings) that do not cover the garment. No sunglasses, no hats, no bags."
  },
  "pose": {
    "stance": "standing straight and still, facing the camera, feet slightly apart, full body from head to toe",
    "arms": "both hands resting naturally on the waistband or on the hips, so the waistband of the garment is visible and framed by her hands",
    "gaze": "the woman must look directly into the camera",
    "head_position": "her face must remain naturally oriented toward the camera",
    "full_body_visibility": "The complete garment and the female subject's full body must remain clearly visible from head to toe, with some floor visible below her shoes."
  },
  "photography": {
    "camera_style": "Casual smartphone UGC video frame, recorded by another person holding a phone in front of her.",
    "angle": "Frontal, straight-on, at roughly chest height, slightly below eye level so the legs look long. Not from above.",
    "shot_type": "Vertical full-body shot, the woman centered, occupying most of the frame height.",
    "aspect_ratio": "9:16 vertical",
    "camera_movement": "Subtle realistic handheld micro-vibrations, otherwise static.",
    "focus": "The entire image must remain naturally sharp and realistic, without artificial background blur, portrait mode, bokeh or cinematic depth of field.",
    "visual_style": "Realistic everyday smartphone footage with natural sharpness and authentic UGC appearance, like a fashion try-on video filmed in a shop.",
    "quality": "Ultra-photorealistic, highly detailed and authentic smartphone UGC aesthetic.",
    "restrictions": [
      "The woman must maintain direct eye contact with the camera.",
      "Do not show her looking away, at the ground or to the sides.",
      "Do not define or reproduce any specific woman, face, body, hair, skin tone or physical appearance.",
      "Do not use any cinematic effect, artificial background blur, portrait mode or professional photography effects.",
      "The background must remain clearly visible and naturally detailed.",
      "Do not make the image look like a film, fashion campaign or commercial production.",
      "No text, no logos, no watermarks, no captions anywhere in the image.",
      "The result must look like a real casual smartphone recording made inside an ordinary clothing store."
    ]
  },
  "background": {
    "setting": "The inside of a real, bright clothing store or showroom: garment racks and shelves with folded clothes behind and beside her, a clean floor (light tiles, wood or a large rug), track lighting or large windows, maybe a full-length mirror in the distance.",
    "instructions": [
      "Do not specify or reproduce any real brand, store name, logo or recognizable shop.",
      "Choose a completely different random store interior for every generation.",
      "Racks may hold garments in neutral, muted tones so they do not compete with the referenced garment.",
      "Leave a clear aisle around the woman: nothing in front of her, nothing obstructing the garment.",
      "The background must remain clearly visible, detailed and in natural focus.",
      "The store must look realistic, tidy, well lit and lived-in, with no people close to the camera."
    ]
  },
  "lighting": {
    "type": "Bright, even retail lighting (ceiling spotlights or daylight through large windows), the kind of light that shows the true color of the fabric.",
    "direction": "Frontal and from above, soft, with no hard shadows over the garment.",
    "effect": "Realistic exposure, natural skin tones, true fabric color, subtle smartphone auto-exposure.",
    "restrictions": [
      "Do not use dramatic cinematic lighting.",
      "Do not use colored or moody lighting that would shift the color of the garment.",
      "Do not create a stylized film look or commercial fashion lighting."
    ]
  },
  "atmosphere": {
    "mood": "Casual, spontaneous, realistic try-on video in a clothing store: a friend showing you a garment she just tried on.",
    "randomization": "The woman, her identity, face, age, body, hair, skin tone, shoes, small accessories and the store must be completely random in every generation. Only the referenced garment (and its exact color) and the plain white fitted top are fixed.",
    "final_style": "The final result must look like a real, unedited frame from a smartphone video recorded inside an ordinary clothing store, with no cinematic appearance, no artificial blur and no professional photography effects."
  }
}
