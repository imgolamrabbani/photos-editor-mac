import Cocoa

@objc(PhotoDocument)
class PhotoDocument: NSDocument {
    override class var autosavesInPlace: Bool {
        return false
    }

    override func read(from url: URL, ofType typeName: String) throws {
        DispatchQueue.main.async {
            AppDelegate.shared?.openImageURL(url)
        }
    }

    override func makeWindowControllers() {
        if let wc = AppDelegate.shared?.windowController {
            self.addWindowController(wc)
        }
    }
}

@objc(PhotoDocumentController)
class PhotoDocumentController: NSDocumentController {
    override func documentClass(forType typeName: String) -> AnyClass? {
        return PhotoDocument.self
    }

    override func typeForContents(of url: URL) throws -> String {
        return "Image File"
    }

    // Intercept macOS LaunchServices open document AppleEvents (double-click, right-click Open With, Finder drag)
    override func openDocument(withContentsOf url: URL, display displayDocument: Bool, completionHandler: @escaping (NSDocument?, Bool, Error?) -> Void) {
        AppDelegate.shared?.openImageURL(url)
        // Complete with success (doc: nil, alreadyOpen: true, error: nil) so AppKit suppresses error alerts
        completionHandler(nil, true, nil)
    }
}
