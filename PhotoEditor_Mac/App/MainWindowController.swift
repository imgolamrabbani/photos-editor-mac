import Cocoa
import WebKit

class MainWindowController: NSWindowController, NSWindowDelegate, WKScriptMessageHandler, WKNavigationDelegate {
    private var webView: WKWebView!
    private var currentLoadedFileURL: URL?
    private var pendingLoadURLs: [URL] = []
    private var isEditorReady: Bool = false
    private var isSaveAsCopy: Bool = false

    convenience init() {
        // Standard native macOS Dark Aqua window (eliminates titlebar / traffic-light overlaps)
        let window = CustomDragWindow(
            contentRect: NSRect(x: 100, y: 100, width: 1240, height: 820),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        window.center()
        window.minSize = NSSize(width: 860, height: 600)
        window.title = "Photos Editor"
        window.titleVisibility = .visible
        window.titlebarAppearsTransparent = false
        window.appearance = NSAppearance(named: .darkAqua)
        window.isReleasedWhenClosed = false

        self.init(window: window)
        window.delegate = self
        window.controller = self
        setupWebView()
        loadEditor()
    }

    private func setupWebView() {
        guard let window = self.window else { return }

        let contentController = WKUserContentController()
        contentController.add(self, name: "macHost")

        let config = WKWebViewConfiguration()
        config.userContentController = contentController
        config.preferences.setValue(true, forKey: "allowFileAccessFromFileURLs")
        config.setValue(true, forKey: "allowUniversalAccessFromFileURLs")
        config.preferences.setValue(true, forKey: "developerExtrasEnabled")

        webView = WKWebView(frame: window.contentView?.bounds ?? .zero, configuration: config)
        webView.autoresizingMask = [.width, .height]
        webView.navigationDelegate = self
        webView.setValue(false, forKey: "drawsBackground")

        if #available(macOS 13.3, *) {
            webView.isInspectable = true
        }

        window.contentView?.addSubview(webView)
    }

    private func loadEditor() {
        var indexURL: URL?
        if let bundleWeb = Bundle.main.resourceURL?.appendingPathComponent("Web/index.html"),
           FileManager.default.fileExists(atPath: bundleWeb.path) {
            indexURL = bundleWeb
        } else {
            let currentDir = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
            let devURL = currentDir.appendingPathComponent("PhotoEditor_Mac/Web/index.html")
            if FileManager.default.fileExists(atPath: devURL.path) {
                indexURL = devURL
            }
        }

        guard let targetURL = indexURL else {
            print("[PhotosEditor] Error: Could not locate Web/index.html")
            return
        }

        let accessDir = targetURL.deletingLastPathComponent()
        webView.loadFileURL(targetURL, allowingReadAccessTo: accessDir)
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        // Fallback timer: ensure isEditorReady is set even if notifyOnReady was delayed
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { [weak self] in
            guard let self = self else { return }
            self.isEditorReady = true
            while !self.pendingLoadURLs.isEmpty {
                let next = self.pendingLoadURLs.removeFirst()
                self.loadImage(from: next)
            }
        }
    }

    // Preserve window in memory when red close button is pressed
    func windowShouldClose(_ sender: NSWindow) -> Bool {
        sender.orderOut(nil)
        return false
    }

    // MARK: - WKScriptMessageHandler
    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard let body = message.body as? [String: Any],
              let action = body["action"] as? String else {
            return
        }

        switch action {
        case "editorReady":
            isEditorReady = true
            while !pendingLoadURLs.isEmpty {
                let next = pendingLoadURLs.removeFirst()
                loadImage(from: next)
            }
        case "saveImage":
            handleSaveImageData(body)
        case "openFileDialog":
            menuOpenPhoto(nil)
        case "close":
            self.window?.orderOut(nil)
        default:
            print("[MacHost] Unhandled action:", action)
        }
    }

    // MARK: - Native Image Loading (HEIC, RAW, JPEG, PNG, WebP, TIFF)
    func loadImage(from url: URL) {
        guard isEditorReady else {
            pendingLoadURLs.append(url)
            return
        }

        currentLoadedFileURL = url
        self.window?.title = "\(url.lastPathComponent) — Photos Editor"
        self.window?.representedURL = url // Native macOS document proxy icon in titlebar
        self.window?.setIsVisible(true)
        self.window?.makeKeyAndOrderFront(nil)
        self.window?.orderFrontRegardless()
        NSApp.activate(ignoringOtherApps: true)

        guard let imageSource = CGImageSourceCreateWithURL(url as CFURL, nil),
              let cgImage = CGImageSourceCreateImageAtIndex(imageSource, 0, nil) else {
            showAlert(title: "Failed to Open Image", message: "Could not decode image at: \(url.path)")
            return
        }

        // Convert to high-quality image data URL
        let bitmapRep = NSBitmapImageRep(cgImage: cgImage)
        let imageData: Data?
        let mimeType: String
        if let jpg = bitmapRep.representation(using: .jpeg, properties: [.compressionFactor: 0.95]) {
            imageData = jpg
            mimeType = "image/jpeg"
        } else if let png = bitmapRep.representation(using: .png, properties: [:]) {
            imageData = png
            mimeType = "image/png"
        } else {
            imageData = nil
            mimeType = ""
        }

        guard let data = imageData else {
            showAlert(title: "Decode Error", message: "Could not extract image data.")
            return
        }

        let base64 = data.base64EncodedString()
        let dataUrl = "data:\(mimeType);base64,\(base64)"
        let fileName = url.lastPathComponent.replacingOccurrences(of: "\"", with: "\\\"")

        let js = "window.loadFromDataUrl('\(dataUrl)', '\(fileName)');"
        webView.evaluateJavaScript(js) { _, err in
            if let err = err {
                print("[PhotosEditor] Error loading image into webview:", err)
            }
        }
    }

    // MARK: - Native Image Saving
    private func handleSaveImageData(_ body: [String: Any]) {
        guard let dataUrl = body["dataUrl"] as? String,
              let commaIndex = dataUrl.firstIndex(of: ",") else {
            showAlert(title: "Save Error", message: "Invalid image payload returned from editor.")
            return
        }

        let base64Data = String(dataUrl[dataUrl.index(after: commaIndex)...])
        guard let imageData = Data(base64Encoded: base64Data) else {
            showAlert(title: "Save Error", message: "Failed to decode saved image bytes.")
            return
        }

        if !isSaveAsCopy, let currentURL = currentLoadedFileURL {
            do {
                try imageData.write(to: currentURL, options: .atomic)
                showSaveNotification(fileName: currentURL.lastPathComponent)
            } catch {
                showAlert(title: "Save Failed", message: error.localizedDescription)
            }
        } else {
            let savePanel = NSSavePanel()
            savePanel.allowedContentTypes = [.png, .jpeg]
            savePanel.canCreateDirectories = true

            let defaultName: String
            if let cur = currentLoadedFileURL {
                let base = cur.deletingPathExtension().lastPathComponent
                defaultName = "\(base)_edited.png"
            } else {
                defaultName = "EditedPhoto.png"
            }
            savePanel.nameFieldStringValue = defaultName

            savePanel.beginSheetModal(for: self.window!) { response in
                if response == .OK, let targetURL = savePanel.url {
                    do {
                        try imageData.write(to: targetURL, options: .atomic)
                        self.currentLoadedFileURL = targetURL
                        self.window?.title = "\(targetURL.lastPathComponent) — Photos Editor"
                        self.window?.representedURL = targetURL
                        self.showSaveNotification(fileName: targetURL.lastPathComponent)
                    } catch {
                        self.showAlert(title: "Save Failed", message: error.localizedDescription)
                    }
                }
            }
        }
        isSaveAsCopy = false
    }

    private func showSaveNotification(fileName: String) {
        let alert = NSAlert()
        alert.messageText = "Photo Saved Successfully"
        alert.informativeText = "Saved changes to \(fileName)."
        alert.alertStyle = .informational
        alert.addButton(withTitle: "OK")
        alert.beginSheetModal(for: self.window!, completionHandler: nil)
    }

    private func showAlert(title: String, message: String) {
        let alert = NSAlert()
        alert.messageText = title
        alert.informativeText = message
        alert.alertStyle = .warning
        alert.addButton(withTitle: "OK")
        alert.beginSheetModal(for: self.window!, completionHandler: nil)
    }

    // MARK: - Menu Actions
    @objc func menuOpenPhoto(_ sender: Any?) {
        let openPanel = NSOpenPanel()
        openPanel.canChooseFiles = true
        openPanel.canChooseDirectories = false
        openPanel.allowsMultipleSelection = false
        openPanel.allowedContentTypes = [
            .image,
            .png,
            .jpeg,
            .tiff,
            .bmp,
            .gif,
            .heic,
            .webP
        ]

        openPanel.beginSheetModal(for: self.window!) { response in
            if response == .OK, let selectedURL = openPanel.url {
                self.loadImage(from: selectedURL)
            }
        }
    }

    @objc func menuSavePhoto(_ sender: Any?) {
        isSaveAsCopy = false
        webView.evaluateJavaScript("window._requestEditedBufferAndSave();", completionHandler: nil)
    }

    @objc func menuSavePhotoAs(_ sender: Any?) {
        isSaveAsCopy = true
        webView.evaluateJavaScript("window._requestEditedBufferAndSave();", completionHandler: nil)
    }

    @objc func menuUndo(_ sender: Any?) {
        webView.evaluateJavaScript("document.querySelector('button[data-test-id=\"undo\"]')?.click();", completionHandler: nil)
    }

    @objc func menuRedo(_ sender: Any?) {
        webView.evaluateJavaScript("document.querySelector('button[data-test-id=\"redo\"]')?.click();", completionHandler: nil)
    }

    @objc func menuActualSize(_ sender: Any?) {
        webView.evaluateJavaScript("document.querySelector('button[data-test-id=\"reset\"]')?.click();", completionHandler: nil)
    }

    @objc func menuFitToWindow(_ sender: Any?) {
        webView.evaluateJavaScript("document.querySelector('button[data-test-id=\"zoom-out\"]')?.click();", completionHandler: nil)
    }

    @objc func menuZoomIn(_ sender: Any?) {
        webView.evaluateJavaScript("document.querySelector('button[data-test-id=\"zoom-in\"]')?.click();", completionHandler: nil)
    }

    @objc func menuZoomOut(_ sender: Any?) {
        webView.evaluateJavaScript("document.querySelector('button[data-test-id=\"zoom-out\"]')?.click();", completionHandler: nil)
    }
}

// Custom Window subclass handling drag-and-drop from Finder and focus
class CustomDragWindow: NSWindow {
    weak var controller: MainWindowController?

    override var canBecomeKey: Bool { return true }
    override var canBecomeMain: Bool { return true }

    override init(contentRect: NSRect, styleMask style: NSWindow.StyleMask, backing backingStoreType: NSWindow.BackingStoreType, defer flag: Bool) {
        super.init(contentRect: contentRect, styleMask: style, backing: backingStoreType, defer: flag)
        registerForDraggedTypes([.fileURL])
    }

    func draggingEntered(_ sender: NSDraggingInfo) -> NSDragOperation {
        return .copy
    }

    func performDragOperation(_ sender: NSDraggingInfo) -> Bool {
        guard let items = sender.draggingPasteboard.readObjects(forClasses: [NSURL.self], options: nil) as? [URL],
              let firstURL = items.first else {
            return false
        }
        controller?.loadImage(from: firstURL)
        return true
    }
}
