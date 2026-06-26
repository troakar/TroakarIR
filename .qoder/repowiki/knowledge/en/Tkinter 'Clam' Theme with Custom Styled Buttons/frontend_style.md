The Troakar Physical Acoustic Synthesis Orchestrator uses a **Tkinter** (specifically `tkinterdnd2.TkinterDnD`) GUI with the standard **`ttk`** widget set. The visual style is defined by the built-in **'clam'** theme, applied globally in `main.py`. 

### Key Styling Elements:
1.  **Theme Base**: The application explicitly sets `style.theme_use('clam')` in `main.py`, providing a clean, modern-ish look compared to the default system theme.
2.  **Custom Button Styles**: In `ui/tab_taichi.py`, specific `ttk.Style` configurations are used to create distinct visual cues for primary actions:
    *   `Taichi.TButton`: Uses **purple** foreground text and **Arial 11 bold** font for the FDTD simulation trigger.
    *   `Texture.TButton`: Uses **darkcyan** foreground text and **Arial 11 bold** font for the friction texture synthesis trigger.
3.  **Layout & Spacing**: The UI relies heavily on `grid` geometry management with explicit `padding` (e.g., `padding="15"`, `padding=(0, 0, 15, 0)`) and `sticky` alignments to create structured panels. 
4.  **Visual Feedback**: 
    *   **Status Bar**: A gray foreground label (`foreground="gray"`) at the bottom provides status updates.
    *   **Dynamic Labels**: Several labels use colored text (`foreground="darkcyan"`, `foreground="purple"`, `foreground="orangered"`, `foreground="gold"`, `foreground="blue"`) to highlight dynamic values like scale, duration, and physical parameters.
    *   **Canvas Visualization**: The `TaichiTab` uses `tk.Canvas` with a dark background (`bg="#111"`) and colored highlights (`highlightbackground="#444"`) to display instrument masks and sensor positions (Red for strike, Yellow/Orange for pickups).
5.  **Font Usage**: The interface consistently uses **Arial** in various sizes (9, 10, 11) and weights (normal, bold, italic) for labels, buttons, and descriptions. Italic gray text is used for descriptive hints.

### Developer Conventions:
*   Use `ttk` widgets over `tk` widgets for consistency with the 'clam' theme.
*   Apply custom styles via `ttk.Style().configure()` only when distinct color coding is needed for primary actions.
*   Use `foreground` color arguments directly on `ttk.Label` widgets for dynamic value highlighting.
*   Maintain consistent padding and grid structures for a balanced layout across tabs.