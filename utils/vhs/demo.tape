# demo.tape
# Set up the terminal
Output docs/demo.gif
Set FontSize 16
Set Width 1400
Set Height 600
Set Padding 40
Set WindowBar Colorful
Set Theme "Catppuccin Mocha"

# Start the demo
Type "alias breakfast='$(pwd)/.venv/bin/python3 ./breakfast'"
Enter
Ctrl+L
Sleep 1s
Type "# Serving up a fresh breakfast..."
Sleep 500ms
Enter
Sleep 1s

# Show the help command
Type "breakfast --help"
Sleep 500ms
Enter
Sleep 3s

# Clear and show a real-world example
Ctrl+L
Type "breakfast -o psf -r requests"
Sleep 500ms
Enter

# Wait for the breakfast emoji progress spinner to finish
# (Timed at 15s + 10% buffer)
Sleep 17s

# Admire the table
Sleep 8s

# End with a flourish
Type "# Tasty!"
Sleep 500ms
Enter
Sleep 2s
