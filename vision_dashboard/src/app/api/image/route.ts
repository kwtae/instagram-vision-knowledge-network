import { NextRequest, NextResponse } from "next/server";
import fs from "fs";
import path from "path";

export async function GET(req: NextRequest) {
    const url = new URL(req.url);
    const filepath = url.searchParams.get("path");

    if (!filepath) {
        return new NextResponse("File path missing", { status: 400 });
    }

    try {
        // Resolve absolute path
        const resolvedPath = path.resolve(process.cwd(), "..", filepath);

        const w = url.searchParams.get("w");
        const h = url.searchParams.get("h");

        // check existence
        if (!fs.existsSync(resolvedPath)) {
            return new NextResponse("File not found", { status: 404 });
        }

        const mimeType = resolvedPath.endsWith(".txt") ? "text/plain"
            : resolvedPath.endsWith(".png") ? "image/png"
                : resolvedPath.endsWith(".jpg") || resolvedPath.endsWith(".jpeg") ? "image/jpeg"
                    : resolvedPath.endsWith(".pdf") ? "application/pdf"
                        : "application/octet-stream";

        // Resize if requested
        if ((w || h) && (mimeType === "image/png" || mimeType === "image/jpeg")) {
            try {
                const sharp = (await import('sharp')).default;
                let transform = sharp(resolvedPath);
                if (w || h) {
                    transform = transform.resize(w ? parseInt(w) : null, h ? parseInt(h) : null, { fit: 'inside' });
                }
                const buffer = await transform.toBuffer();
                return new NextResponse(buffer as any, {
                    headers: {
                        "Content-Type": mimeType,
                        "Content-Length": buffer.length.toString(),
                        "Cache-Control": "public, max-age=86400"
                    }
                });
            } catch (e) {
                console.warn("Sharp resizing failed, falling back to original", e);
            }
        }

        const stat = fs.statSync(resolvedPath);
        const fileStream = fs.createReadStream(resolvedPath);

        // @ts-ignore
        return new NextResponse(fileStream, {
            headers: {
                "Content-Type": mimeType,
                "Content-Length": stat.size.toString(),
                "Cache-Control": "public, max-age=3600"
            }
        });

    } catch (error: any) {
        console.error("API error serving image:", error);
        return new NextResponse(error.message, { status: 500 });
    }
}
