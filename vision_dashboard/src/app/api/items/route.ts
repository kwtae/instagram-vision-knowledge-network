import { NextRequest, NextResponse } from "next/server";
import { exec } from "child_process";
import path from "path";
import util from "util";

const execPromise = util.promisify(exec);

export async function GET(req: NextRequest) {
    const url = new URL(req.url);
    const limit = url.searchParams.get("limit") || "50";
    const offset = url.searchParams.get("offset") || "0";
    const tag = url.searchParams.get("tag") || "";
    const q = url.searchParams.get("q") || "";

    try {
        const parentDir = path.resolve(process.cwd(), "..");
        const pythonScript = path.join(parentDir, "query_api.py");
        // Ensure we are using the venv python
        const pythonExe = path.join(parentDir, "venv", "Scripts", "python.exe");

        let cmd = `"${pythonExe}" "${pythonScript}" limit=${limit} offset=${offset}`;
        if (tag) {
            cmd += ` tag=${tag}`;
        }
        if (q) {
            cmd += ` q="${q}"`;
        }

        const { stdout, stderr } = await execPromise(cmd, { cwd: parentDir });

        if (stderr) {
            console.warn("Python stderr:", stderr);
        }

        // Attempt to parse stdout as JSON
        const lines = stdout.trim().split("\n");
        // Find the line that actually contains JSON (to skip potential warnings)
        let jsonStr = "";
        for (let i = lines.length - 1; i >= 0; i--) {
            if (lines[i].startsWith("{")) {
                jsonStr = lines[i];
                break;
            }
        }

        const parsed = JSON.parse(jsonStr);
        return NextResponse.json(parsed);
    } catch (error: any) {
        console.error("API error:", error);
        return NextResponse.json({ success: false, error: error.message }, { status: 500 });
    }
}
