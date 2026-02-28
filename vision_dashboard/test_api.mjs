import { exec } from "child_process";
import path from "path";
import util from "util";

const execPromise = util.promisify(exec);

async function test() {
    try {
        const parentDir = path.resolve(process.cwd(), "..");
        const pythonScript = path.join(parentDir, "query_api.py");
        const pythonExe = path.join(parentDir, "venv", "Scripts", "python.exe");

        let cmd = `"${pythonExe}" "${pythonScript}" limit=1`;
        console.log("Running:", cmd);

        const { stdout, stderr } = await execPromise(cmd, { cwd: parentDir });
        console.log("Stdout lines:", stdout.split('\n').length);
        console.log("Stdout tail:", stdout.slice(-200));

        const lines = stdout.trim().split("\n");
        let jsonStr = "";
        for (let i = lines.length - 1; i >= 0; i--) {
            if (lines[i].trim().startsWith("{")) {
                jsonStr = lines[i].trim();
                break;
            }
        }

        console.log("JSON FOUND:", jsonStr.substring(0, 50));
        const parsed = JSON.parse(jsonStr);
        console.log("Parse Success! Items counts:", parsed.count);
    } catch (e) {
        console.error("FAILED:", e);
    }
}
test();
