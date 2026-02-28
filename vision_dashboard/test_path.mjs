import path from "path";
import fs from "fs";

async function test_image_path() {
    console.log("CWD:", process.cwd());
    const filepath = "./watched_files/instagram/ig_DVREluWkZwH_20260228_051905_0.png";
    const resolvedPath_with_dotdot = path.resolve(process.cwd(), "..", filepath);
    const resolvedPath_direct = path.resolve(process.cwd(), filepath);

    console.log("Resolved with ..:", resolvedPath_with_dotdot);
    console.log("Exists with ..:", fs.existsSync(resolvedPath_with_dotdot));

    console.log("Resolved directly:", resolvedPath_direct);
    console.log("Exists directly:", fs.existsSync(resolvedPath_direct));
}
test_image_path();
