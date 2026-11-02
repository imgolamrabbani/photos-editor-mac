import Cocoa

// 1. Initialize custom document controller early to handle LaunchServices document routing
let photoDocController = PhotoDocumentController()

// 2. Initialize application and assign application delegate
let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate

// 3. Start standard AppKit main run loop
_ = NSApplicationMain(CommandLine.argc, CommandLine.unsafeArgv)
