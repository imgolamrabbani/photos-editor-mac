import Cocoa

// 1. Initialize application and assign application delegate
let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate

// 2. Start standard AppKit main run loop
_ = NSApplicationMain(CommandLine.argc, CommandLine.unsafeArgv)
