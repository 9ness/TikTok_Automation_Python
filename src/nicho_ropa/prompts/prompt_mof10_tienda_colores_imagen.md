<!-- "TIENDA COLORES · 15 SEGUNDOS EN DOS CLIPS" (MUJER), paso 1 de 3: la
     IMAGEN, en Flow con la foto de la prenda como referencia.

     NO es un formato del curso: sale de cinco vídeos virales de pantalones de
     mujer (sep 2026) que comparten la misma receta —una chica en una tienda
     de ropa con top blanco ajustado, cuerpo entero de frente, el pantalón
     puesto; arranca nombrando tres o cuatro colores y en cada color el
     pantalón cambia de golpe (es un corte de edición, no una toma nueva);
     luego enseña la cintura y los bolsillos, se da la vuelta, se agacha y
     cierra con "varios colores en tienda".

     Esta imagen es el PRIMER fotograma del clip 1. La pose sale de la
     FAMILIA de la prenda (`config.con_familia`): un pantalón a medio poner
     —el "guau" de los virales—, un jersey al que se le tira del bajo, un
     cárdigan que se abre… El plano 1 del clip
     es subírselo mientras nombra los colores. Los cortes de color NO se
     generan en Flow: al montar, la app recolorea el fotograma del instante
     en que nombra cada color (con el pantalón a la altura que esté).

     La segunda imagen (`prompt_mof10_tienda_colores_imagen2.md`) es la misma
     chica de espaldas, en la misma tienda: es el arranque del clip 2.

     La chica: joven (20-25) y con pinta de creadora de moda, como en los
     virales. Con "random adult 20-32" y "random body type" salían mujeres
     que aparentaban 35-40 y el operador lo rechazó (sep 2026). -->

{
  "subject": {
    "description": "A young, attractive adult woman (early twenties), like a stylish fashion content creator, standing in three-quarter view (body slightly turned, face to the camera) inside a real clothing store, wearing the referenced garment and settling it: {{POSE_IMAGEN}} She looks at the camera. Her identity, face, body, hair, skin tone, age and overall appearance must be entirely random in every generation. She is being recorded in a casual UGC style with a smartphone by another person. Her full body must be visible from head to toe.",
    "appearance": "entirely random",
    "age": "young adult, clearly between 20 and 25 years old, fresh and youthful look (never older-looking, never a teenager)",
    "expression": "natural, confident, charming smile, lively and expressive, as if about to start talking",
    "gaze": "direct eye contact with the camera",
    "head_orientation": "naturally facing the camera",
    "hair": "long, glossy, well-groomed hair (random color and texture), worn loose, in soft waves or in a sleek high ponytail",
    "body_type": "{{CUERPO_IMAGEN}}",
    "skin_tone": "completely random natural skin tone"
  },
  "clothing": {
    "source": "The female subject MUST wear exactly the garment shown in the provided reference image.",
    "instructions": [
      "Use the provided reference image exclusively as the garment reference.",
      "The female subject wears the exact garment shown in the reference image, in the exact same color, and it keeps its full original length, cut and proportions.",
      "Do not crop, shorten or restyle the garment: it looks exactly like the reference, only worn.",
      "Replicate every detail with maximum accuracy: color, fabric, texture, seams, pleats, waistband, drawstring, buttons, pockets, fit, cut, length and proportion.",
      "Do not reinterpret, redesign, replace, simplify, recolor, add or omit any part of the referenced garment.",
      "The referenced garment must remain exactly the same and must be the main visual focus, fully visible from the waistband to the hem.",
      "{{ROPA_BASE}}",
      "Shoes: simple and neutral (white or light grey sneakers, or plain sandals or flats), chosen to match the garment; never shoes that draw attention.",
      "No jacket, coat, bag, belt or any garment that covers or overlaps the referenced garment, unless a belt is part of the reference image.",
      "The complete outfit must look clean, simple and coordinated: the garment is the star and the rest of the outfit is a neutral canvas.",
      "The garment is the only fixed visual element. The woman and the store must be completely different and random in every generation."
    ]
  },
  "face": {
    "instructions": "Generate a completely random, attractive, youthful adult female face (early twenties), with harmonious features. Do not follow, reproduce or imitate any specific facial identity, facial description or predefined appearance.",
    "skin_texture": "fresh, healthy, glowing young skin, natural and realistic, with visible pores and no excessive retouching",
    "makeup": "soft natural glam makeup: groomed brows, subtle mascara, glowy skin, nude lips"
  },
  "accessories": {
    "instructions": "Preserve any accessories visible in the reference image. Otherwise at most small, discreet accessories (thin bracelets, small earrings) that do not cover the garment. No sunglasses, no hats, no bags."
  },
  "pose": {
    "stance": "standing in a THREE-QUARTER turn (body turned about 30-45 degrees away from the camera, face still towards it), feet slightly apart, full body from head to toe",
    "arms": "{{MANOS_IMAGEN}}",
    "gaze": "the woman must look directly into the camera",
    "head_position": "her face must remain naturally oriented toward the camera",
    "full_body_visibility": "The female subject's full body must remain clearly visible from head to toe, with some floor visible below her shoes, and the referenced garment fully visible with its real colour and fabric."
  },
  "photography": {
    "camera_style": "Casual smartphone UGC video frame, recorded by another person holding a phone in front of her.",
    "angle": "Straight-on at roughly chest height, slightly below eye level so the legs look long, with her body in three-quarter view. Not from above.",
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
      "INDOORS ONLY: she is INSIDE the store, never outdoors, never in a patio, a street or the doorway. The season is only visible through the shop windows and in the light.",
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
    "randomization": "The woman, her identity, face, hair color, skin tone, shoes, small accessories and the store must be completely random in every generation. Only the referenced garment (and its exact color) and the base outfit described above are fixed.",
    "final_style": "The final result must look like a real, unedited frame from a smartphone video recorded inside an ordinary clothing store, with no cinematic appearance, no artificial blur and no professional photography effects."
  }
}
