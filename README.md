## Website Tracker

This repository contains a tool designed to track how people interact with a website and play back those sessions later. It captures mouse movements, clicks, scrolling, and typing.

---

### How it Works

The system is divided into three main parts:

1. **The Tracker (Browser)**
A small script sits on a website. It watches what the user does and sends that data to a collection server. It uses compression to make sure the data transfers quickly without slowing down the website.
2. **The Monitor (Client)**
A central hub that receives the data. It shows a live dashboard in your terminal where you can see counts of clicks and movements in real-time. It automatically saves all this activity into simple text files (CSV).
3. **The Replayer (Recreator)**
A web interface that reads the saved data files. It recreates the website and moves a "fake" cursor to show exactly where the user went. It can also group keystrokes together to show what the user typed in specific boxes.

---

### Folder Structure

* **`browserpeer/`**: Contains the tracking script and a demo page to test it.
* **`client/`**: The Python application that runs the terminal dashboard and saves data.
* **`recreator/`**: The web application used to watch recorded sessions.
* **`docker-compose.yml`**: A file to start the entire system at once using containers.

---

### Getting Started

#### Using Docker (Recommended)

If you have Docker installed, you can start everything by running:
`docker-compose up`

* The **Monitor** will be available at: `http://localhost:8000`
* The **Replayer** will be available at: `http://localhost:5000`

#### Manual Setup

1. **Install requirements**: Run `pip install -r requirements.txt` in both the `client` and `recreator` folders.
2. **Start the Monitor**: Run `python client/app.py`.
3. **Start the Replayer**: Run `python recreator/app.py`.

---

### Dashboard Controls

When the Monitor is running in your terminal, you can use these keys:

* **r**: Reset all saved data.
* **c**: Clear the current view.
* **s**: Open the Replayer in your browser.
* **q**: Quit the program.
