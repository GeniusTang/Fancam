import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/upload": "http://localhost:8000",
      "/sse": "http://localhost:8000",
      "/analysis": "http://localhost:8000",
      "/generate": "http://localhost:8000",
      "/thumbnails": "http://localhost:8000",
      "/download": "http://localhost:8000",
      "/merge": "http://localhost:8000",
      "/fragments": "http://localhost:8000",
      "/frame-sample": "http://localhost:8000",
      "/reassign": "http://localhost:8000",
      "/preview": "http://localhost:8000",
      "/preview-video": "http://localhost:8000",
      "/health": "http://localhost:8000",
    },
  },
});
