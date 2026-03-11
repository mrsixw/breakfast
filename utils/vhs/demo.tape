# demo.tape
# Set up the terminal
Output docs/demo.gif
Set FontSize 16
Set Width 1200
Set Height 600
Set Padding 40
Set WindowBar Colorful
Set Theme "Catppuccin Mocha"

# Start the demo
Type "# Serving up a fresh breakfast..."
Sleep 500ms
Enter
Sleep 1s

# Show the help command
Type "./breakfast --help"
Sleep 500ms
Enter
Sleep 3s

# Clear and show a real-world example
Ctrl+L
Type "./breakfast -o google -r python"
Sleep 500ms
Enter

# Wait for the breakfast emoji progress spinner to finish
Sleep 15s

# Admire the table
Sleep 8s

# End with a flourish
Type "# Tasty!"
Sleep 500ms
Enter
Sleep 2s
