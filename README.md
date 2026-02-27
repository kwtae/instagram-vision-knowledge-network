# MCP Vision Knowledge Network

An autonomous, local-first system that seamlessly ingests images, text, and documents, processes them using private Vision AI models, and builds a hierarchical, Obsidian-style interactive network graph.

## Core Features

1. **Intelligent Auto-Scraping (Jitter & Fault Tolerance)**
   - Includes a fully automated Instagram saved-post scraper designed to run indefinitely in the background.
   - **Anti-Bot Mechanism**: Uses randomized delays (Jitter) between 8 to 15 minutes to mimic human behavior and evade rate limits.
   - **Self-Healing**: Implements retry logic if network dropouts occur, preventing premature termination.

2. **Perceptual Image Hashing (Duplicate Pruning)**
   - Computes a perceptual hash (`phash`) of incoming images before they are passed to the LLM.
   - Visually identical images (e.g., repeating backgrounds in carousels) are instantly identified and deleted, conserving disk space and drastically reducing GPU/LLM inference loads.

3. **Obsidian-Style Visualization (D3.js)**
   - Generates an interactive web-based graph (`network_graph.html`) mirroring the minimalist aesthetics of Obsidian's Light Theme.
   - Features dynamic node sizing based on degree centrality, modern minimalist color palettes, and a hidden, hover-activated toolbar.
   - Dragged nodes maintain their coordinates (Sticky Nodes) allowing users to manually sculpt the graph structure over time.

4. **Manual Contextual Relinking**
   - Enables users to define their own relationships between data nodes natively within the browser UI.
   - **Shift+Click** sequentially on two distinct nodes will forge a custom edge, saving the new topology to the local database automatically.

## System Architecture

- **Extraction Layer**: Playwright (Headless Web Automation), PyTesseract (OCR), PyMuPDF (PDF Extraction)
- **Vision & LLM Layer**: Local Ollama Server running `gpt-oss:20b` for taxonomy classification and semantic image generation.
- **Knowledge Base**: ChromaDB for vector storage and relationship inference based on cosine similarity of text embeddings.
- **Presentation Layer**: D3.js and Vanilla CSS, hosted via an embedded real-time HTTP Node Server on port `8080`.

## Installation & Deployment

Ensure you have Python 3.10+ installed and a local instance of Ollama active on your machine.

1. Clone the repository and navigate to the project root.
2. Initialize your virtual environment and install dependencies:
   ```bash
   python -m venv venv
   .\venv\Scripts\Activate
   pip install -r requirements.txt
   pip install imagehash scipy
   ```
3. Prepare the necessary token files. You must provide a valid `cookies.json` file in the root directory for Instagram authentication.

## Usage Guide

You need two console windows to operate the full pipeline.

### 1. Database & Visualization Server
Run the primary backend server which monitors files, processes them through the AI, and hosts the visualizer UI.
```bash
.\venv\Scripts\python.exe main.py
```
*Note: The frontend is accessible at `http://localhost:8080` (or by opening `network_graph.html` directly). Keep this running strictly in the background to handle the Two-Way binding updates for Tagging and Manual Relinking.*

### 2. Autonomous Scraper
In a separate terminal, launch the daemon that continuously feeds new data into the pipeline.
```bash
.\venv\Scripts\python.exe auto_scraper.py
```
The scraper will fetch the latest saved entries, deposit them into the watched folder, and hibernate for a randomized interval to protect your account standing.

## Interaction Mechanics within the Graph

- **Search**: Hover over the top-left Search bar to reveal advanced details and toggle the Timeline view. Filtering strictly highlights relevant targets.
- **Open Source File**: Standard Left-Click on a node.
- **Edit Tags**: Right-Click on a node to update its semantic categories. Changes reflect instantly.
- **Custom Links**: Hold `Shift` and Left-Click the Source Node, then hold `Shift` and Left-Click the Target Node. A dashed red line will instantly connect them, persisting across all future sessions.
