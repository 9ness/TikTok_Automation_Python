<!-- MARCA PERSONAL · Zapatos Multi Escena 10s. Prompt de IMAGEN, literal del
     curso. Dos imágenes adjuntas: el personaje de referencia y el zapato. El
     outfit NO es el producto: se genera a juego con el calzado. Habla de
     `video_start` porque lo que describe es la composición del primer
     fotograma, que es justo la foto que hay que generar. -->

{
  "references": {
    "character_reference": "Use the provided character reference image exclusively to reproduce the female character.",
    "product_reference": "Use the provided product reference image exclusively to reproduce the product.",
    "styling_rule": "The female character from the character reference image must wear a coordinated autumn outfit that matches the style, colors and materials of the product reference."
  },
  "video_start": {
    "first_frame": "The video must begin exactly from the close-up composition shown in the provided reference image.",
    "instructions": [
      "Preserve the initial seated pose, product placement, close camera angle and tight framing shown in the reference image.",
      "Frame the woman closely from approximately the chest down, prioritizing her legs, hands and the product.",
      "The product must occupy the lower foreground and remain large, sharp and clearly visible.",
      "Place the scene inside an aesthetic vintage home with a warm autumn atmosphere.",
      "Do not begin with a fade, transition, zoom or introductory movement.",
      "Remove all text, captions, logos, buttons, icons, search bars, playback symbols, graphics, interface elements and watermarks.",
      "Naturally reconstruct every area hidden by the original graphics.",
      "Do not reproduce fire, flames, embers, smoke or an illuminated fireplace."
    ]
  },
  "subject": {
    "description": "The exact adult female character shown in the provided character reference image, seated close to the camera inside an aesthetic vintage house with a warm autumn atmosphere. She wears an elegant autumn outfit coordinated with the product shown in the provided product reference image.",
    "gender": "female",
    "age": "preserve the exact apparent adult age shown in the character reference image",
    "identity": "match the female character reference image with maximum visual accuracy",
    "instructions": [
      "The subject is not random.",
      "Reproduce exactly the same female character shown in the provided character reference image.",
      "Preserve her identity, body type, body proportions, skin tone, hairstyle, hair color, hands, nails and every visible physical characteristic.",
      "Do not generate a different person or alter her physical appearance.",
      "The woman must wear clothing that visually coordinates with the referenced product.",
      "The upper part of her face may remain outside the frame because this is a close product-focused composition.",
      "Her movements must be subtle, natural and physically continuous."
    ]
  },
  "outfit": {
    "source": "Generate an autumn outfit specifically coordinated with the product shown in the provided product reference image.",
    "style": "feminine, modern, elegant, cozy, vintage-inspired and suitable for autumn",
    "instructions": [
      "Analyze the product's exact colors, materials, visual style and design before creating the outfit.",
      "Dress the female character in an outfit that matches and complements the referenced product naturally.",
      "Use harmonious or complementary autumn colors drawn from the product's palette.",
      "The outfit must look intentionally styled with the referenced product as one complete coordinated look.",
      "Suitable garments may include a knitted sweater, cardigan, fitted top, autumn dress, skirt, leggings, trousers, coat or other clothing that naturally matches the product.",
      "Choose garments according to the product rather than using the same random outfit in every generation.",
      "Do not copy clothing from the character reference image unless it coordinates perfectly with the referenced product.",
      "Do not cover or obstruct the product.",
      "Do not add unrelated logos, brand names, patterns or graphic prints.",
      "Once generated, the complete outfit must remain identical throughout the video.",
      "No garment may change color, material, shape, fit or design.",
      "No garment may appear, disappear, duplicate or transform."
    ]
  },
  "product": {
    "instructions": [
      "The referenced product is the main visual focus of the shot.",
      "Reproduce the product from the provided product reference image with maximum visual accuracy.",
      "Preserve its exact design, shape, colors, materials, textures, stitching, accessories, sole, details and proportions.",
      "Position the product prominently in the lower foreground, close to the camera.",
      "Keep the product large, sharp, recognizable and unobstructed.",
      "The woman's outfit must coordinate naturally with the product without altering its original appearance.",
      "The product must never appear, disappear, duplicate, transform, switch position magically or move by itself."
    ]
  },
  "hands_and_nails": {
    "instructions": [
      "Preserve the woman's hand shape and skin tone.",
      "Use feminine, elegant nails in a color that subtly coordinates with the product and outfit.",
      "Add only discreet rings that complement the complete autumn look.",
      "Her hands may gently touch or adjust the product using realistic physical contact.",
      "Do not generate additional hands, extra fingers, fused fingers, duplicated nails or floating accessories."
    ]
  },
  "pose_and_action": {
    "starting_pose": "Begin in the same close seated pose and product arrangement shown in the reference image.",
    "movement": "The woman makes small natural movements, gently running one hand over the referenced product and briefly highlighting its material or visible details while keeping it close to the camera.",
    "instructions": [
      "Preserve the initial placement of her legs, hands, clothing and product.",
      "Movements must begin smoothly from the starting frame.",
      "Keep the product as the dominant element throughout the video.",
      "Do not stand up or change to a wide shot.",
      "Do not move the product away from the foreground.",
      "Do not use cuts, transitions, teleportation or sudden pose changes.",
      "Do not interchange, replace or duplicate the product."
    ]
  },
  "camera": {
    "style": "authentic vertical lifestyle UGC video recorded with a smartphone",
    "angle": "low, intimate and slightly front-facing angle directed toward the seated woman and the referenced product",
    "shot_type": "tight medium close-up product shot, approximately from the chest down",
    "composition": "the woman fills most of the frame while the referenced product occupies the lower foreground and appears prominently close to the lens",
    "aspect_ratio": "9:16 vertical",
    "movement": "mostly static handheld camera with only subtle natural micro-movements",
    "focus": "sharp focus on the product, hands and coordinated outfit, with the vintage background slightly softer",
    "quality": "ultra-photorealistic smartphone video with realistic skin, fabric, product and environmental textures",
    "restrictions": [
      "No wide or full-body shot.",
      "No distant framing.",
      "No cuts or transitions.",
      "No initial zoom.",
      "No sudden reframing.",
      "No additional people, bodies or hands.",
      "No text, captions, subtitles or typography.",
      "No logos or promotional labels.",
      "No search bars, interfaces or application UI.",
      "No playback buttons or shopping icons.",
      "No graphics, emojis or animated overlays.",
      "No borders, banners or watermarks.",
      "No fire, flames, glowing embers, sparks, smoke, lit candles or burning objects.",
      "No active, illuminated or burning fireplace."
    ]
  },
  "background": {
    "setting": "inside a cozy aesthetic vintage house with an elegant autumn atmosphere and no visible fire",
    "visual_style": "authentic vintage European-inspired home, warm, nostalgic, intimate and refined",
    "color_palette": "warm brown, dark wood, caramel, beige, cream, terracotta, rust, burgundy and olive green",
    "possible_elements": [
      "dark wooden furniture",
      "a Persian-style rug in muted autumn tones",
      "warm electric vintage lamps",
      "textured cushions and knitted blankets",
      "ceramic vases",
      "subtle dried autumn branches",
      "tasteful vintage decorative objects",
      "wooden shelves or an antique sideboard"
    ],
    "instructions": [
      "The environment must clearly be inside a real aesthetic vintage house.",
      "Keep the background visible enough to establish the autumn atmosphere without distracting from the product.",
      "The background must remain secondary and slightly softer because the framing is close.",
      "Do not include a fireplace whenever possible.",
      "If an architectural fireplace is present, it must be completely unlit, cold, empty and free of flames, embers, smoke or glow.",
      "Do not include lit candles, bonfires, wood stoves or any source of visible fire.",
      "Do not create a Halloween setting.",
      "Avoid excessive pumpkins, leaves or theatrical decorations.",
      "No background object may appear, disappear, float or move by itself."
    ]
  },
  "lighting": {
    "type": "soft warm autumn lighting created exclusively by diffused natural window light and warm electric vintage lamps",
    "effect": "cozy golden illumination with soft natural shadows and clearly visible product details",
    "product_priority": "The referenced product, hands and coordinated outfit must be evenly illuminated.",
    "consistency": "Lighting, exposure, white balance and shadows must remain stable throughout the video.",
    "restrictions": [
      "Do not use firelight.",
      "Do not generate flickering orange light.",
      "Do not simulate illumination from flames, candles, embers or a fireplace."
    ]
  },
  "continuity": {
    "instructions": [
      "Maintain strict physical continuity from the first frame to the final frame.",
      "Preserve the same woman, coordinated outfit, referenced product, accessories, pose and vintage autumn interior.",
      "Avoid morphing, flickering, warping, anatomy changes and visual jumps.",
      "The product must retain exactly the same design, shape, colors, materials, details and proportions.",
      "Nothing may appear, disappear, duplicate or transform between frames.",
      "All movement must follow realistic human motion and physical interaction."
    ]
  },
  "audio": {
    "music": "none",
    "dialogue": "none",
    "sound": "only subtle realistic indoor room sounds and natural clothing or product-handling sounds",
    "restrictions": [
      "No music.",
      "No voice-over.",
      "No artificial sound effects.",
      "No crackling fire sounds.",
      "No interface or notification sounds."
    ]
  },
  "negative_prompt": [
    "mismatched outfit",
    "clothing that clashes with the product",
    "random clothing",
    "fire",
    "flames",
    "burning fireplace",
    "lit fireplace",
    "fireplace glow",
    "embers",
    "sparks",
    "smoke",
    "lit candles",
    "bonfire",
    "burning objects",
    "text",
    "captions",
    "graphics",
    "logos",
    "watermarks",
    "interface elements"
  ],
  "atmosphere": {
    "mood": "close, intimate, warm, cozy, sophisticated, vintage and autumnal lifestyle UGC without any fire",
    "consistency": "The female character, coordinated autumn outfit, referenced product and vintage autumn home must remain visually consistent throughout the video."
  }
}
