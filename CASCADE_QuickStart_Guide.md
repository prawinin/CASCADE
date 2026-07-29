# CASCADE 

This guide provides step-by-step instructions for getting the **CASCADE** (Computational Architecture for Sketching, Conformation, ADMET, and Docking Evaluation) platform running on your local computer, designed specifically for users without a strong programming background.

## Prerequisites

Before starting, you need one essential piece of software that acts as the "engine" for CASCADE:
* **Docker Desktop**: Download and install it for free from [Docker's official website](https://www.docker.com/products/docker-desktop/). 
  *(Note: You do not need to create a Docker account. Just ensure the Docker Desktop application is open and running in the background before proceeding).*

## Step 1: Download the Software

You can download the CASCADE source code using either the **Point-and-Click Method** or the **Command Line Method**.

### Option A: Point-and-Click Method (Easiest)
1. Go to the CASCADE official GitHub repository: [https://github.com/prawinin/CASCADE](https://github.com/prawinin/CASCADE)
2. Click the green **"<> Code"** button near the top right of the page.
3. Select **"Download ZIP"** from the dropdown menu.
4. Locate the downloaded ZIP file in your Downloads folder and extract/unzip it to a convenient location on your computer (for example, your Desktop).

### Option B: Command Line Method (Fastest)
If you prefer to use the terminal and already have Git installed, you can download the code directly. Open your terminal and paste this command:
```bash
git clone https://github.com/prawinin/CASCADE.git
cd CASCADE
```

## Step 2: Open Your Terminal

If you used Option A above to download the ZIP, you must now open a terminal exactly inside the folder you just extracted.

* **On Windows 11:** 
  1. Open the extracted `CASCADE` folder in File Explorer.
  2. Right-click anywhere in the empty white space inside the folder.
  3. Select **"Open in Terminal"**.
* **On Windows 10:** 
  1. Open the extracted `CASCADE` folder in File Explorer.
  2. Hold down the `Shift` key on your keyboard and right-click in the empty space.
  3. Select **"Open PowerShell window here"** or **"Open Command Prompt here"**.
* **On Mac (macOS):** 
  1. Open the extracted `CASCADE` folder in Finder.
  2. Right-click (or two-finger tap) the folder.
  3. Go to **Services** -> **New Terminal at Folder**.
  *(If you don't see this option, you can also open the "Terminal" app, type `cd ` with a space, and drag-and-drop the CASCADE folder directly into the Terminal window, then press Enter).*
* **On Linux:** 
  1. Open the extracted folder in your file manager.
  2. Right-click in the empty space and select **"Open in Terminal"**.

## Step 3: Start the CASCADE Server

With your terminal open inside the CASCADE folder, you can now start the software. 
There are two ways to start the software depending on your computer's setup. 

### Option A: The Universal Launcher (If you have Python installed)
Type the following command and press Enter:
```bash
python compose_up.py
```
*The launcher will automatically build the environment, start the servers, and immediately pop open your web browser right to the CASCADE interface!*

### Option B: The Direct Method (If you do not have Python installed)
Type the following command and press Enter:
```bash
docker compose up -d
```
1. Wait about 60 seconds for the engine to boot up.
2. Open your web browser (like Google Chrome or Safari) and manually navigate to: `http://127.0.0.1:7860`

## Step 4: Shutting Down

When you are finished using CASCADE and want to completely turn it off to free up your computer's resources:
1. Go back to your terminal window (ensure you are still inside the CASCADE folder).
2. Type the following command and press Enter:
   ```bash
   docker compose down
   ```
*(Note: Because of Docker's caching, starting the software next time will be nearly instantaneous!)*
