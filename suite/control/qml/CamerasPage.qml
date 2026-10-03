import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.Page {
    id: page
    padding: Kirigami.Units.smallSpacing
    topPadding: 0
    bottomPadding: Kirigami.Units.smallSpacing

    property string cam: startCam
    property var s: bridge.cameraSettings(cam)
    property var groups: bridge.cameraControls(cam)
    property var sizes: bridge.cameraSizes(cam)
    property var presetList: bridge.presets(cam)
    property int presetIndex: 0
    property var fs: ({})
    property real peak: 1
    readonly property bool showHints: false
    property bool advanced: bridge.uiSetting("camAdvanced", false)
    readonly property bool wide: width > Kirigami.Units.gridUnit * 40
    readonly property var activePreset: presetList.find(p => p.current)

    function reload() { s = bridge.cameraSettings(cam); groups = bridge.cameraControls(cam); sizes = bridge.cameraSizes(cam); presetReload() }
    function presetReload() {
        presetList = bridge.presets(cam)
        const i = presetList.findIndex(p => p.current)
        if (i >= 0) presetIndex = i
        else if (presetIndex >= presetList.length) presetIndex = 0
    }
    function sizeIndex() {
        for (let i = 0; i < sizes.length; i++)
            if (sizes[i].minWidth === s.minWidth) return i
        return 0
    }
    function setLocal(key, value) { const o = {}; o[key] = value; s = Object.assign({}, s, o) }
    function edit(key, value) { setLocal(key, value); bridge.setCameraSetting(cam, key, value) }

    onCamChanged: { bridge.stopPreview(); peak = 1; reload(); autoStart.restart() }
    Component.onCompleted: autoStart.start()
    Component.onDestruction: bridge.stopPreview()
    Connections { target: bridge; function onCameraChanged() { page.reload() } function onPresetsChanged() { page.presetReload() } }

    // the preview starts by itself: the page is for looking at what the sliders do
    Timer { id: autoStart; interval: 400; onTriggered: if (!bridge.busy) bridge.startPreview(page.cam) }
    Timer {
        interval: 250; repeat: true; running: bridge.previewCamera === page.cam
        onTriggered: {
            page.fs = bridge.focusState(page.cam)
            if (page.fs.sharpness !== undefined) page.peak = Math.max(page.peak * 0.995, page.fs.sharpness)
        }
    }
    Timer { interval: 2000; repeat: true; running: page.visible; onTriggered: page.presetReload() }

    // ---- a titled box: the title says what the group of options below it is ----
    component Section: Rectangle {
        id: sec
        property string title
        default property alias content: body.data
        Layout.fillWidth: true
        implicitHeight: col.implicitHeight + Kirigami.Units.largeSpacing * 2
        radius: 8
        color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.045)
        ColumnLayout {
            id: col
            anchors { left: parent.left; right: parent.right; top: parent.top; margins: Kirigami.Units.largeSpacing }
            spacing: Kirigami.Units.smallSpacing
            RowLayout {
                spacing: Kirigami.Units.smallSpacing
                Rectangle { width: 3; height: Kirigami.Units.gridUnit * 1.1; radius: 2; color: Kirigami.Theme.highlightColor }
                QQC2.Label { text: sec.title; font.bold: true; font.pointSize: Kirigami.Theme.defaultFont.pointSize + 1 }
            }
            ColumnLayout { id: body; Layout.fillWidth: true; spacing: Kirigami.Units.smallSpacing }
        }
    }
    component Hint: QQC2.Label {
        visible: page.showHints
        Layout.fillWidth: true
        wrapMode: Text.WordWrap
        opacity: 0.6
        font.pointSize: Kirigami.Theme.defaultFont.pointSize - 1
    }

    // ---- name dialog for save / rename / duplicate ----
    QQC2.Dialog {
        id: nameDialog
        property string mode: "save"
        property string error: ""
        property string targetId: ""
        modal: true
        anchors.centerIn: QQC2.Overlay.overlay
        title: mode === "save" ? "Save the current settings as a preset" : mode === "rename" ? "Rename preset" : "Duplicate preset"
        standardButtons: QQC2.Dialog.Ok | QQC2.Dialog.Cancel
        contentItem: ColumnLayout {
            spacing: Kirigami.Units.smallSpacing
            QQC2.Label { text: "Name (" + page.cam + " camera):" }
            QQC2.TextField { id: nameField; Layout.fillWidth: true; Layout.minimumWidth: Kirigami.Units.gridUnit * 18; onAccepted: nameDialog.accept() }
            QQC2.Label { text: nameDialog.error; visible: text.length > 0; color: Kirigami.Theme.negativeTextColor }
        }
        function begin(m, id, initial) { mode = m; targetId = id; error = ""; nameField.text = initial; open(); nameField.forceActiveFocus(); nameField.selectAll() }
        onAccepted: {
            let r
            if (mode === "save") {
                r = bridge.savePreset(page.cam, nameField.text, false)
                if (r === "exists") { overwriteDialog.name = nameField.text; overwriteDialog.open(); return }
            } else if (mode === "rename") r = bridge.renamePreset(page.cam, targetId, nameField.text)
            else r = bridge.duplicatePreset(page.cam, targetId, nameField.text)
            if (r === "invalid") { error = "Please type a name."; open() }
            else if (r === "exists") { error = "A preset with that name already exists."; open() }
        }
    }
    QQC2.Dialog {
        id: overwriteDialog
        property string name: ""
        modal: true
        anchors.centerIn: QQC2.Overlay.overlay
        title: "Replace preset?"
        standardButtons: QQC2.Dialog.Yes | QQC2.Dialog.No
        contentItem: QQC2.Label { text: "A preset called \"" + overwriteDialog.name + "\" exists. Replace it with the current settings?"; wrapMode: Text.WordWrap }
        onAccepted: bridge.savePreset(page.cam, overwriteDialog.name, true)
    }
    QQC2.Dialog {
        id: deleteDialog
        property string pid: ""
        property string name: ""
        modal: true
        anchors.centerIn: QQC2.Overlay.overlay
        title: "Delete preset?"
        standardButtons: QQC2.Dialog.Yes | QQC2.Dialog.No
        contentItem: QQC2.Label { text: "Delete the preset \"" + deleteDialog.name + "\"? This cannot be undone."; wrapMode: Text.WordWrap }
        onAccepted: bridge.deletePreset(page.cam, deleteDialog.pid)
    }
    QQC2.Dialog {
        id: updateDialog
        property string pid: ""
        property string name: ""
        modal: true
        anchors.centerIn: QQC2.Overlay.overlay
        title: "Update preset?"
        standardButtons: QQC2.Dialog.Yes | QQC2.Dialog.No
        contentItem: QQC2.Label { text: "Replace the settings stored in \"" + updateDialog.name + "\" with the current ones?"; wrapMode: Text.WordWrap }
        onAccepted: bridge.savePreset(page.cam, updateDialog.name, true)
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: Kirigami.Units.smallSpacing

        // front / rear: the same buttons as everywhere else in the panel
        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: Kirigami.Units.largeSpacing
            Layout.bottomMargin: Kirigami.Units.smallSpacing
            Layout.leftMargin: Kirigami.Units.largeSpacing
            Layout.rightMargin: Kirigami.Units.largeSpacing
            spacing: Kirigami.Units.smallSpacing
            Repeater {
                model: [{ t: "Front camera", c: "front", i: "camera-web-symbolic" }, { t: "Rear camera", c: "rear", i: "camera-photo-symbolic" }]
                delegate: QQC2.Button { Layout.fillWidth: true; QQC2.ToolTip.text: (typeof tips !== "undefined" && tips[text]) || ""; QQC2.ToolTip.visible: hovered && QQC2.ToolTip.text.length > 0; QQC2.ToolTip.delay: 500;
                    text: modelData.t
                    icon.name: modelData.i
                    checkable: true
                    checked: page.cam === modelData.c
                    autoExclusive: true
                    highlighted: checked
                    onClicked: page.cam = modelData.c
                }
            }
        }

        GridLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            columns: page.wide ? 2 : 1
            columnSpacing: Kirigami.Units.gridUnit * 1.5
            rowSpacing: Kirigami.Units.smallSpacing

            // ---------------- left: fixed preview, presets, hints switch ----------------
            ColumnLayout {
                Layout.alignment: Qt.AlignTop
                Layout.fillWidth: true
                Layout.fillHeight: page.wide
                spacing: Kirigami.Units.smallSpacing

                Item {
                    id: previewArea
                    Layout.fillWidth: true
                    Layout.fillHeight: page.wide
                    Layout.preferredHeight: page.wide ? 0 : Math.min(width * 0.75, page.height * 0.34)
                    Layout.minimumHeight: Kirigami.Units.gridUnit * 7
                    // the frames are 4:3: a box of that shape has no black bars
                    Rectangle {
                        anchors.centerIn: parent
                        width: Math.min(parent.width, parent.height * 4 / 3)
                        height: width * 3 / 4
                        color: "black"
                        radius: 4
                        clip: true
                        Image {
                            anchors.fill: parent
                            fillMode: Image.Stretch
                            cache: false
                            source: bridge.previewCamera === page.cam ? "image://preview/" + bridge.previewFrame : ""
                            visible: bridge.previewCamera === page.cam
                        }
                        QQC2.Label {
                            anchors.centerIn: parent
                            width: parent.width - 2 * Kirigami.Units.largeSpacing
                            horizontalAlignment: Text.AlignHCenter
                            wrapMode: Text.WordWrap
                            color: "white"
                            visible: bridge.previewCamera !== page.cam
                            text: bridge.previewError.length > 0 ? bridge.previewError : (bridge.busy ? "Please wait..." : "Live preview is off")
                        }
                    }
                }
                RowLayout {
                    Layout.alignment: Qt.AlignHCenter
                    QQC2.Button { QQC2.ToolTip.text: (typeof tips !== "undefined" && tips[text]) || ""; QQC2.ToolTip.visible: hovered && QQC2.ToolTip.text.length > 0; QQC2.ToolTip.delay: 500;
                        text: bridge.previewCamera === page.cam ? "Pause preview" : "Start preview"
                        icon.name: bridge.previewCamera === page.cam ? "media-playback-pause" : "media-playback-start"
                        enabled: !bridge.busy
                        onClicked: bridge.previewCamera === page.cam ? bridge.stopPreview() : bridge.startPreview(page.cam)
                    }
                    QQC2.BusyIndicator { running: bridge.busy; visible: bridge.busy; implicitWidth: Kirigami.Units.gridUnit * 1.6; implicitHeight: implicitWidth }
                }

                // ---- presets ----
                Section {
                    title: "Presets (" + page.cam + " camera)"
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.smallSpacing
                        QQC2.ComboBox {
                            Layout.fillWidth: true
                            enabled: page.presetList.length > 0
                            model: page.presetList.length > 0 ? page.presetList.map(p => p.name + (p.current ? "   (active)" : "")) : ["No presets saved yet"]
                            currentIndex: page.presetIndex
                            onActivated: i => page.presetIndex = i
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Kirigami.Units.smallSpacing
                            QQC2.Button { QQC2.ToolTip.text: (typeof tips !== "undefined" && tips[text]) || ""; QQC2.ToolTip.visible: hovered && QQC2.ToolTip.text.length > 0; QQC2.ToolTip.delay: 500;
                                Layout.fillWidth: true
                                text: "Apply"
                                icon.name: "dialog-ok-apply"
                                enabled: page.presetList.length > 0 && !bridge.busy
                                onClicked: bridge.applyPreset(page.cam, page.presetList[page.presetIndex].id)
                            }
                            QQC2.Button { QQC2.ToolTip.text: (typeof tips !== "undefined" && tips[text]) || ""; QQC2.ToolTip.visible: hovered && QQC2.ToolTip.text.length > 0; QQC2.ToolTip.delay: 500;
                                Layout.fillWidth: true
                                text: "Save as..."
                                icon.name: "document-save-as"
                                onClicked: nameDialog.begin("save", "", "")
                            }
                            QQC2.Button {
                                text: "More"
                                icon.name: "view-more-symbolic"
                                enabled: page.presetList.length > 0
                                onClicked: moreMenu.popup()
                                QQC2.ToolTip.text: "More: update, rename, duplicate, delete"
                                QQC2.ToolTip.visible: hovered
                                QQC2.Menu {
                                    id: moreMenu
                                    readonly property var p: page.presetList.length > 0 ? page.presetList[Math.min(page.presetIndex, page.presetList.length - 1)] : ({ id: "", name: "" })
                                    QQC2.MenuItem { text: "Update with the current settings..."; icon.name: "document-save"; onTriggered: { updateDialog.pid = moreMenu.p.id; updateDialog.name = moreMenu.p.name; updateDialog.open() } }
                                    QQC2.MenuItem { text: "Rename..."; icon.name: "edit-rename"; onTriggered: nameDialog.begin("rename", moreMenu.p.id, moreMenu.p.name) }
                                    QQC2.MenuItem { text: "Duplicate..."; icon.name: "edit-copy"; onTriggered: nameDialog.begin("duplicate", moreMenu.p.id, moreMenu.p.name + " copy") }
                                    QQC2.MenuSeparator {}
                                    QQC2.MenuItem { text: "Delete..."; icon.name: "edit-delete"; onTriggered: { deleteDialog.pid = moreMenu.p.id; deleteDialog.name = moreMenu.p.name; deleteDialog.open() } }
                                }
                            }
                        }
                        QQC2.Label {
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                            opacity: 0.7
                            font.pointSize: Kirigami.Theme.defaultFont.pointSize - 1
                            text: page.activePreset ? "Current settings = \"" + page.activePreset.name + "\"" : "Current settings do not match a preset"
                        }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    QQC2.Switch { QQC2.ToolTip.text: (typeof tips !== "undefined" && tips[text]) || ""; QQC2.ToolTip.visible: hovered && QQC2.ToolTip.text.length > 0; QQC2.ToolTip.delay: 500;
                        text: "Advanced"
                        checked: page.advanced
                        onToggled: { page.advanced = checked; bridge.setUiSetting("camAdvanced", checked) }
                    }
                    Item { Layout.fillWidth: true }
                }
                Hint { text: "Changes apply to every app using the " + page.cam + " camera. While the preview runs other apps cannot use this camera: pause it before a video call." }
            }

            // ---------------- right: the adjustments, the only part that scrolls ----------------
            QQC2.ScrollView {
                id: scroll
                Layout.preferredWidth: page.wide ? Kirigami.Units.gridUnit * 21 : -1
                Layout.maximumWidth: page.wide ? Kirigami.Units.gridUnit * 23 : -1
                Layout.fillWidth: !page.wide
                Layout.fillHeight: true
                contentWidth: availableWidth
                clip: true

                ColumnLayout {
                    width: scroll.availableWidth - Kirigami.Units.largeSpacing
                    spacing: Kirigami.Units.largeSpacing

                    // ---- focus (rear only: the front lens is fixed) ----
                    Section {
                        title: "Focus"
                        visible: page.cam === "rear"
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: Kirigami.Units.smallSpacing
                            RowLayout {
                                Layout.fillWidth: true
                                QQC2.Label { text: "Manual focus"; font.bold: true }
                                Item { Layout.fillWidth: true }
                                QQC2.Switch { QQC2.ToolTip.text: (typeof tips !== "undefined" && tips[text]) || ""; QQC2.ToolTip.visible: hovered && QQC2.ToolTip.text.length > 0; QQC2.ToolTip.delay: 500;
                                    checked: page.s.focusManual
                                    onToggled: { bridge.setCameraSetting(page.cam, "focusManual", checked ? 1 : 0); page.reload() }
                                }
                            }
                            Hint {
                                text: page.s.focusManual
                                      ? "The lens stays where you put it in every app until you switch back to automatic focus."
                                      : "Automatic focus is on. Switch to manual to place the lens yourself; it starts from where the autofocus is now."
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                QQC2.Label { text: "Lens position"; Layout.fillWidth: true }
                                ValueField {
                                    enabled: page.s.focusManual
                                    from: 0; to: 1023; step: 1
                                    value: focusSlider.value
                                    onCommitted: v => { focusSlider.value = v; page.edit("focus", v) }
                                }
                                QQC2.Label { text: "/ 1023"; opacity: 0.7 }
                            }
                            QQC2.Slider {
                                id: focusSlider
                                Layout.fillWidth: true
                                Layout.preferredHeight: Kirigami.Units.gridUnit * 2.6
                                enabled: page.s.focusManual
                                from: 0; to: 1023; stepSize: 1
                                onMoved: page.edit("focus", value)
                            }
                            // follows the stored value in manual mode and the live lens position in auto mode, except while it is being dragged
                            Binding {
                                target: focusSlider; property: "value"
                                value: page.s.focusManual ? page.s.focus : (page.fs.focus !== undefined ? page.fs.focus : 0)
                                when: !focusSlider.pressed
                                restoreMode: Binding.RestoreNone
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                enabled: page.s.focusManual
                                spacing: Kirigami.Units.smallSpacing
                                Repeater {
                                    model: [{ t: "-50", d: -50 }, { t: "-5", d: -5 }, { t: "+5", d: 5 }, { t: "+50", d: 50 }]
                                    delegate: QQC2.Button { QQC2.ToolTip.text: (typeof tips !== "undefined" && tips[text]) || ""; QQC2.ToolTip.visible: hovered && QQC2.ToolTip.text.length > 0; QQC2.ToolTip.delay: 500;
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: Kirigami.Units.gridUnit * 2.4
                                        text: modelData.t
                                        onClicked: { const v = Math.max(0, Math.min(1023, Math.round(focusSlider.value) + modelData.d)); focusSlider.value = v; page.edit("focus", v) }
                                    }
                                }
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                QQC2.Label { text: "Sharpness meter"; Layout.fillWidth: true }
                                QQC2.ProgressBar {
                                    Layout.preferredWidth: Kirigami.Units.gridUnit * 9
                                    from: 0; to: 1
                                    value: page.fs.sharpness !== undefined ? Math.min(1, page.fs.sharpness / page.peak) : 0
                                }
                            }
                            Hint { text: "The bar shows how sharp the picture is compared with the sharpest moment seen: move the lens until it is as full as it gets. Use the small buttons for fine steps." }
                        }
                    }

                    // ---- output ----
                    Section {
                        title: "Output"
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: Kirigami.Units.smallSpacing
                            RowLayout { QQC2.Label { text: "Picture size offered to apps"; font.bold: true } }
                            QQC2.ComboBox {
                                Layout.fillWidth: true
                                model: page.sizes.map(x => x.text)
                                currentIndex: page.sizeIndex()
                                enabled: !bridge.busy
                                onActivated: bridge.setCameraSetting(page.cam, "minWidth", page.sizes[currentIndex].minWidth)
                            }
                            Hint { text: "Apps take the first size offered. Smaller sizes run faster (calls, Zoom); the largest give the sharpest photos. Changing it restarts the camera service." }
                        }
                    }

                    // ---- the sliders, one titled box per group ----
                    Repeater {
                        model: page.groups
                        delegate: Section {
                            title: modelData.group
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 0
                                Repeater {
                                    model: modelData.items
                                    delegate: SettingSlider {
                                        visible: !modelData.adv || page.advanced
                                        label: modelData.label
                                        desc: modelData.desc
                                        showHints: page.showHints
                                        from: modelData.min
                                        to: modelData.max
                                        step: modelData.step
                                        unit: modelData.unit
                                        defaultValue: modelData.default
                                        modelValue: page.s[modelData.key]
                                        names: modelData.key === "temporal" ? ["off", "low", "medium", "high", "stronger", "maximum"] : null
                                        onEdited: value => page.edit(modelData.key, value)
                                        onResetRequested: { page.setLocal(modelData.key, modelData.default); bridge.resetCameraSetting(page.cam, modelData.key) }
                                    }
                                }
                            }
                        }
                    }

                    // ---- geometry ----
                    Section {
                        title: "Geometry"
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: Kirigami.Units.smallSpacing
                            RowLayout {
                                Layout.fillWidth: true
                                QQC2.Label { text: "Mirror (left-right)"; font.bold: true }
                                Item { Layout.fillWidth: true }
                                QQC2.Switch { QQC2.ToolTip.text: (typeof tips !== "undefined" && tips[text]) || ""; QQC2.ToolTip.visible: hovered && QQC2.ToolTip.text.length > 0; QQC2.ToolTip.delay: 500; checked: page.s.mirror; onToggled: bridge.setCameraSetting(page.cam, "mirror", checked ? 1 : 0) }
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                QQC2.Label { text: "Flip (upside-down)"; font.bold: true; Layout.fillWidth: true }
                                QQC2.Switch { QQC2.ToolTip.text: (typeof tips !== "undefined" && tips[text]) || ""; QQC2.ToolTip.visible: hovered && QQC2.ToolTip.text.length > 0; QQC2.ToolTip.delay: 500; checked: page.s.flip; onToggled: bridge.setCameraSetting(page.cam, "flip", checked ? 1 : 0) }
                            }
                            Hint { text: "Done in the sensor, so it costs nothing. It is read when a camera starts: the preview restarts, and open apps must reopen the camera. On the front camera it uses the full sensor mode (about 27 fps at small sizes)." }
                        }
                    }

                    QQC2.Button { QQC2.ToolTip.text: (typeof tips !== "undefined" && tips[text]) || ""; QQC2.ToolTip.visible: hovered && QQC2.ToolTip.text.length > 0; QQC2.ToolTip.delay: 500;
                        text: "Reset all adjustments to the tuned defaults"
                        icon.name: "edit-undo"
                        enabled: page.s.dirty
                        onClicked: bridge.resetCamera(page.cam)
                        Layout.bottomMargin: Kirigami.Units.gridUnit * 2
                    }
                }
            }
        }
    }
}
