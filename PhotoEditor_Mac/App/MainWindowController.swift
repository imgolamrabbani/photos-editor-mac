import Cocoa
import WebKit
import UniformTypeIdentifiers

class MainWindowController: NSWindowController, NSWindowDelegate, WKScriptMessageHandler, WKNavigationDelegate {
    private var webView: WKWebView!
    private var currentLoadedFileURL: URL?
    private var pendingLoadURLs: [URL] = []
    private var isEditorReady: Bool = false
    private var isSaveAsCopy: Bool = false

    convenience init() {
        // Standard native macOS Dark Aqua window
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

        // Allow read access across the filesystem so local photo files can be loaded directly
        webView.loadFileURL(targetURL, allowingReadAccessTo: URL(fileURLWithPath: "/"))
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { [weak self] in
            guard let self = self else { return }
            self.isEditorReady = true
            while !self.pendingLoadURLs.isEmpty {
                let next = self.pendingLoadURLs.removeFirst()
                self.loadImage(from: next)
            }
        }
    }

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
            if let locURL = Bundle.main.url(forResource: "localization_en", withExtension: "json", subdirectory: "Web"),
               let locData = try? Data(contentsOf: locURL),
               let locStr = String(data: locData, encoding: .utf8) {
                let js = "if (typeof window.setLocalizationJson === 'function') { window.setLocalizationJson(JSON.stringify({ strings: \(locStr), locales: ['en-US'] })); }"
                self.webView.evaluateJavaScript(js, completionHandler: nil)
            }
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
        self.window?.representedURL = url
        self.window?.setIsVisible(true)
        self.window?.makeKeyAndOrderFront(nil)
        self.window?.orderFrontRegardless()
        NSApp.activate(ignoringOtherApps: true)

        let ext = url.pathExtension.lowercased()
        let webCompatibleExtensions = ["jpg", "jpeg", "png", "webp", "gif"]

        if webCompatibleExtensions.contains(ext) {
            // Fast direct file loading without decoding overhead
            let fileURLStr = url.absoluteString
            let escapedFileName = url.lastPathComponent
                .replacingOccurrences(of: "\\", with: "\\\\")
                .replacingOccurrences(of: "\"", with: "\\\"")
                .replacingOccurrences(of: "'", with: "\\'")

            let js = "window.loadFromFileUrl('\(fileURLStr)', '\(escapedFileName)');"
            webView.evaluateJavaScript(js) { _, err in
                if let err = err {
                    print("[PhotosEditor] Error loading image from fileUrl:", err)
                }
            }
        } else {
            // High-precision CoreGraphics conversion for HEIC, TIFF, Camera RAW, BMP
            guard let imageSource = CGImageSourceCreateWithURL(url as CFURL, nil),
                  let cgImage = CGImageSourceCreateImageAtIndex(imageSource, 0, nil) else {
                showAlert(title: "Failed to Open Image", message: "Could not decode image at: \(url.path)")
                return
            }

            let bitmapRep = NSBitmapImageRep(cgImage: cgImage)
            guard let jpgData = bitmapRep.representation(using: .jpeg, properties: [.compressionFactor: 0.98]) else {
                showAlert(title: "Decode Error", message: "Could not extract image data.")
                return
            }

            let tempDir = URL(fileURLWithPath: NSTemporaryDirectory())
            let tempCacheURL = tempDir.appendingPathComponent("photos_edit_cache_\(UUID().uuidString).jpg")
            do {
                try jpgData.write(to: tempCacheURL, options: .atomic)
                let escapedFileName = url.lastPathComponent
                    .replacingOccurrences(of: "\\", with: "\\\\")
                    .replacingOccurrences(of: "\"", with: "\\\"")
                    .replacingOccurrences(of: "'", with: "\\'")
                let js = "window.loadFromFileUrl('\(tempCacheURL.absoluteString)', '\(escapedFileName)');"
                webView.evaluateJavaScript(js) { _, err in
                    if let err = err {
                        print("[PhotosEditor] Error loading converted image into webview:", err)
                    }
                }
            } catch {
                showAlert(title: "Cache Error", message: error.localizedDescription)
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

        let saveType = body["saveType"] as? String

        if saveType == "copyClipboard" {
            if let image = NSImage(data: imageData) {
                NSPasteboard.general.clearContents()
                NSPasteboard.general.writeObjects([image])
                showSaveNotification(fileName: "Photo copied to clipboard")
            }
            return
        }

        let isCopy = isSaveAsCopy || (saveType == "saveAsCopy")

        if !isCopy, let currentURL = currentLoadedFileURL {
            do {
                let ext = currentURL.pathExtension.lowercased()
                var finalData = imageData
                if ext == "jpg" || ext == "jpeg" {
                    if let image = NSImage(data: imageData),
                       let tiff = image.tiffRepresentation,
                       let rep = NSBitmapImageRep(data: tiff),
                       let jpg = rep.representation(using: .jpeg, properties: [.compressionFactor: 0.95]) {
                        finalData = jpg
                    }
                }
                try finalData.write(to: currentURL, options: .atomic)
                showSaveNotification(fileName: currentURL.lastPathComponent)
            } catch {
                showAlert(title: "Save Failed", message: error.localizedDescription)
            }
        } else {
            let savePanel = NSSavePanel()
            if #available(macOS 11.0, *) {
                savePanel.allowedContentTypes = [.png, .jpeg]
            } else {
                savePanel.allowedFileTypes = ["png", "jpg", "jpeg"]
            }
            savePanel.canCreateDirectories = true
            savePanel.title = "Save Photo As Copy"
            savePanel.prompt = "Save"

            let defaultName: String
            if let cur = currentLoadedFileURL {
                let base = cur.deletingPathExtension().lastPathComponent
                defaultName = "\(base)_copy.png"
            } else {
                defaultName = "EditedPhoto.png"
            }
            savePanel.nameFieldStringValue = defaultName

            NSApp.activate(ignoringOtherApps: true)
            self.window?.makeKeyAndOrderFront(nil)

            savePanel.beginSheetModal(for: self.window!) { [weak self] response in
                guard let self = self else { return }
                if response == .OK, let targetURL = savePanel.url {
                    do {
                        let ext = targetURL.pathExtension.lowercased()
                        var finalData = imageData
                        if ext == "jpg" || ext == "jpeg" {
                            if let image = NSImage(data: imageData),
                               let tiff = image.tiffRepresentation,
                               let rep = NSBitmapImageRep(data: tiff),
                               let jpg = rep.representation(using: .jpeg, properties: [.compressionFactor: 0.95]) {
                                finalData = jpg
                            }
                        }
                        try finalData.write(to: targetURL, options: .atomic)
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
        if #available(macOS 11.0, *) {
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
        } else {
            openPanel.allowedFileTypes = ["jpg", "jpeg", "png", "heic", "webp", "tiff", "bmp", "gif"]
        }

        openPanel.beginSheetModal(for: self.window!) { response in
            if response == .OK, let selectedURL = openPanel.url {
                self.loadImage(from: selectedURL)
            }
        }
    }

    @objc func menuSavePhoto(_ sender: Any?) {
        isSaveAsCopy = false
        webView.evaluateJavaScript("window.hvcEvents.notifyOnUserSave(0);", completionHandler: nil)
    }

    @objc func menuSavePhotoAs(_ sender: Any?) {
        isSaveAsCopy = true
        webView.evaluateJavaScript("window.hvcEvents.notifyOnUserSave(1);", completionHandler: nil)
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
