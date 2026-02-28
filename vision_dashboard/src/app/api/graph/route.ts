import { NextRequest, NextResponse } from "next/server";
import { exec } from "child_process";
import path from "path";
import util from "util";

const execPromise = util.promisify(exec);

export async function GET(req: NextRequest) {
    try {
        const parentDir = path.resolve(process.cwd(), "..");
        const pythonScript = path.join(parentDir, "query_graph.py");
        const pythonExe = path.join(parentDir, "venv", "Scripts", "python.exe");

        const url = new URL(req.url);
        const limitStr = url.searchParams.get("limit") || "1000";

        // Increased maxBuffer to 50MB because the JSON payload for 6000 nodes is large
        const { stdout, stderr } = await execPromise(`"${pythonExe}" "${pythonScript}" limit=${limitStr}`, { cwd: parentDir, maxBuffer: 1024 * 1024 * 50 });

        if (stderr) {
            console.warn("Python stderr:", stderr);
        }

        // Attempt to parse out the python logs and only get JSON
        const lines = stdout.trim().split("\n");
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
        console.error("API Error executing python graph script:", error);
        return NextResponse.json({ success: false, error: error.message }, { status: 500 });
    }
}
