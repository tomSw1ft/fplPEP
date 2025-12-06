# FPL PEP (Predictive Engine for Points)

An advanced Fantasy Premier League (FPL) companion application designed to help you maximize your points through data-driven optimization and analysis. Built with a modern Python GUI.

## Current Features

- **Dashboard**: Central hub for all tools with a sleek, dark-mode interface .
- **Team Optimization**: Automatically selects your best starting XI, captain, and vice-captain based on predicted points (XP) and fixture difficulty.
- **Tactics Board**: Visualizes your team formation on a pitch view, showing the fixture and predicted points for the gameweek.
- **Transfer Hub**: Analyze the transfer market to find the best replacements by role (GK, DEF, MID, FWD) and budget.
- **Data Hub**: Deep dive into player statistics, now extended to allow for a multi-week plan.
- **Model Performance**: Compare the model's predicted points against actual results for the last 5 gameweeks to verify accuracy.
- **Fixture Difficulty (FDR)**: View, and edit according to your preference, upcoming fixture difficulty ratings to plan ahead.
- **Smart Login**: Supports automatic login via Team ID override.

## Future Features

- **Chip Strategy Helper**: Optimises chip strategy for the user.
- **Real-time Injury Updates**: Move away from FPL "Flags" for player availability.

## Installation

1.  Ensure you have Python installed.
2.  Install the required dependencies:
    ```bash
    pip install pandas requests
    ```
    _(Note: Tkinter is usually included with Python)_

## Usage

1.  Run the application:
    ```bash
    python gui.py
    ```
2.  Enter your **Team ID** when prompted.
    - **Auto-Login**: You can create a `team_id.txt` file in the project root containing your Team ID to skip the login prompt on startup.

## Project Structure

- `gui.py`: The main application entry point and GUI implementation using Tkinter.
- `tool.py`: Core logic for data fetching, XP calculation, and optimization algorithms.
- `custom_fdr.json`: Configuration file for custom fixture difficulty ratings.

---

_Powered by the FPL API._
