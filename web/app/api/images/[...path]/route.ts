import { NextResponse } from "next/server";
import path from "path";
import fs from "fs";

const PROJECT_ROOT = path.resolve(process.cwd(), "..");

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const segments = (await params).path;
  const filePath = path.join(PROJECT_ROOT, ...segments);

  // Security: ensure the resolved path is under PROJECT_ROOT/data/images
  const resolved = path.resolve(filePath);
  const imagesRoot = path.resolve(PROJECT_ROOT, "data", "images");
  if (!resolved.startsWith(imagesRoot)) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  if (!fs.existsSync(resolved)) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  const buffer = fs.readFileSync(resolved);
  const ext = path.extname(resolved).toLowerCase();
  const mimeMap: Record<string, string> = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".txt": "text/plain",
  };

  return new NextResponse(buffer, {
    headers: {
      "Content-Type": mimeMap[ext] || "application/octet-stream",
      "Cache-Control": "public, max-age=86400",
    },
  });
}
