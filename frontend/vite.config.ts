import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const BACKEND = process.env.VITE_BACKEND ?? "http://127.0.0.1:8002";

export default defineConfig({
  plugins: [react()],
  server: { port: 5174, strictPort: true, proxy: { "/api": BACKEND } },
  preview: { port: 5174, strictPort: true, proxy: { "/api": BACKEND } },
});
