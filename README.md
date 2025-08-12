# UmaMusuTrainingHelper
A simple (and VERY bad) training scoring system to assist for new players.
Use in borderless fullscreen


 ## 🎮 Controls

| Key | Action |
|-----|--------|
| `G` | Check **Speed** |
| `H` | Check **Stamina** |
| `J` | Check **Power** |
| `K` | Check **Guts** |
| `L` | Check **Wits** |
| `P` | Reset overlay data |
| `]` | Stops |

## 🖥 How It Works

1. **Template Loading**  
   - Loads all `.png` files from the `templates` folder.

2. **Screen Capture**  
   - Captures the current screen with `pyautogui`.
   - Converts to grayscale for matching.

3. **Matching**  
   - Uses `cv2.matchTemplate` to find matches above a threshold.
   - Suppresses duplicate detections for cleaner results.

4. **Overlay Display**  
   - Tkinter overlay updates every 200ms with current detections.
   - Shows both match names and calculated training value.

5. **Debug Logging**  
   - Saves matched images with bounding boxes into the `debug` folder
  
   
## Notes
It's in no way anywhere NEAR completed. There was so many things for me to add like rainbow training calculation, friendship bar,... but I can't figure out what the most consistent was is without being very weird and broken. I haven't added all characters, so if there's any support card I missed, you can easily manually add it by capturing the icon, in game (use images in templates as reference) and add it manually to templates.
