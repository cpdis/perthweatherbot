# Design preview fixtures

These are **illustrative sample data, not an actual forecast**. The UI displays an explicit preview notice when `preview: true` is present. No exact coordinates are included.

`scene-preview.png` was generated for the local design exploration with the built-in image tool on 11 November 2026. It expands the established miniature-city look into a continuous landscape, with no baked-in dates or weather measurements. It is **not** output from the production Gemini pipeline and is not the production `weather_image.png`.

The production pipeline keeps Gemini 2.5 Flash Image and requests a text-free 16:9 scene. Its new prompt and output handling are covered with offline mocked tests. A real image generation remains to be checked in the authorized production workflow.
