import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    id: page
    title: "Stylus and touch"
    property var s: bridge.stylusInfo()
    Timer { interval: 5000; repeat: true; running: page.visible; onTriggered: page.s = bridge.stylusInfo() }

    // ---- what the pen test has seen ----
    property string state: "none"          // none | away | hover | touch
    property string tool: "-"
    property real pressure: 0
    property real maxPressure: 0
    property var levels: ({})
    property real xTilt: 0
    property real yTilt: 0
    property bool tiltSeen: false
    property real rotation: 0
    property int buttons: 0
    property bool keyRubber: false
    readonly property bool barrelDown: (buttons & Qt.RightButton) !== 0
    readonly property bool rubberDown: (buttons & Qt.MiddleButton) !== 0 || keyRubber || tool === "Eraser"
    property bool eraserSeen: false
    property bool barrelSeen: false
    property bool pressureSeen: false
    property bool eventsSeen: false
    property real lastX: -1
    property real lastY: -1

    function clearTest() {
        canvas.clear()
        maxPressure = 0; levels = ({}); tiltSeen = false; eraserSeen = false; barrelSeen = false; pressureSeen = false
    }

    // The Bluetooth part of the pen (the top button) arrives as an ordinary key press, not as a tablet event:
    // it shows as the rubber/top button while this page has the keyboard focus
    focus: true
    Keys.onPressed: event => { if (!event.isAutoRepeat) { page.keyRubber = true; keyClear.restart() } }
    Timer { id: keyClear; interval: 400; onTriggered: page.keyRubber = false }

    Connections {
        target: tablet
        enabled: page.visible
        function onEvent(e) {
            page.eventsSeen = true
            page.tool = e.tool === "eraser" ? "Eraser" : e.tool === "pen" ? "Tip" : e.tool
            if (e.tool === "eraser") page.eraserSeen = true
            if (e.kind === "leave") { page.state = "away"; page.lastX = -1; return }
            page.pressure = e.pressure
            page.xTilt = e.xTilt; page.yTilt = e.yTilt; page.rotation = e.rotation
            if (Math.abs(e.xTilt) > 0.5 || Math.abs(e.yTilt) > 0.5) page.tiltSeen = true
            page.buttons = e.buttons
            if (e.buttons & Qt.RightButton || e.buttons & Qt.MiddleButton) page.barrelSeen = true
            const touching = e.pressure > 0 || (e.buttons & Qt.LeftButton)
            page.state = touching ? "touch" : "hover"
            if (e.pressure > 0) {
                page.pressureSeen = true
                page.maxPressure = Math.max(page.maxPressure, e.pressure)
                const l = Object.assign({}, page.levels); l[Math.round(e.pressure * 4096)] = 1; page.levels = l
            }
            const p = canvas.mapFromItem(null, e.x, e.y)
            if (touching && p.x >= 0 && p.y >= 0 && p.x <= canvas.width && p.y <= canvas.height) {
                if (page.lastX >= 0) canvas.addSegment(page.lastX, page.lastY, p.x, p.y, e.pressure, e.tool === "eraser")
                page.lastX = p.x; page.lastY = p.y
            } else page.lastX = -1
        }
    }

    ColumnLayout {
        Kirigami.Heading { level: 2; text: page.title }
        spacing: Kirigami.Units.largeSpacing

        Kirigami.InlineMessage {
            Layout.fillWidth: true
            visible: true
            type: s.digitizer.length > 0 ? Kirigami.MessageType.Positive : Kirigami.MessageType.Warning
            text: s.digitizer.length > 0 ? "Touch and pen input detected." : "No touch or pen input found."
        }

        RowLayout { Kirigami.Heading { level: 3; text: "Pen test" } }
        QQC2.Label {
            Layout.fillWidth: true; wrapMode: Text.WordWrap; opacity: 0.7
            text: "Draw in the area below. Line width follows the pressure. Hold the top button (the eraser button of the Surface Pen) and draw to erase. Hover first, press the side button, tilt the pen: the readout shows what the tablet and the pen report."
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Kirigami.Units.largeSpacing
        Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: Kirigami.Units.gridUnit * 15
                Layout.fillHeight: true
                color: "white"
                border.color: Kirigami.Theme.disabledTextColor
                radius: 4
                clip: true
                Canvas {
                    id: canvas
                    anchors.fill: parent
                    property var queue: []
                    function clear() { const c = getContext("2d"); c.clearRect(0, 0, width, height); requestPaint() }
                    function addSegment(x1, y1, x2, y2, p, erase) { queue.push([x1, y1, x2, y2, p, erase]); requestPaint() }
                    onPaint: {
                        const c = getContext("2d")
                        c.lineCap = "round"
                        for (const s of queue) {
                            c.beginPath()
                            c.strokeStyle = s[5] ? "#ffffff" : "#1b3a6b"
                            c.lineWidth = s[5] ? 24 : 1 + s[4] * 14
                            c.moveTo(s[0], s[1]); c.lineTo(s[2], s[3]); c.stroke()
                        }
                        queue = []
                    }
                }
                QQC2.Label { anchors.centerIn: parent; text: page.eventsSeen ? "" : "Touch the screen with the pen here"; color: "#888"; visible: !page.eventsSeen }
                QQC2.Button { QQC2.ToolTip.text: (typeof tips !== "undefined" && tips[text]) || ""; QQC2.ToolTip.visible: hovered && QQC2.ToolTip.text.length > 0; QQC2.ToolTip.delay: 500; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 6; text: "Clear"; icon.name: "edit-clear-all"; onClicked: page.clearTest() }
            }
        // plain grid with fixed-width cells: the readout changes dozens of times a second and a Kirigami.FormLayout re-measures every row on each change
            GridLayout {
                Layout.alignment: Qt.AlignTop
                columns: 2
                columnSpacing: Kirigami.Units.largeSpacing
                rowSpacing: Kirigami.Units.smallSpacing
                component Name: QQC2.Label { Layout.preferredWidth: Kirigami.Units.gridUnit * 6; Layout.alignment: Qt.AlignRight; horizontalAlignment: Text.AlignRight; opacity: 0.7 }
                component Val: QQC2.Label { Layout.preferredWidth: Kirigami.Units.gridUnit * 13; Layout.maximumWidth: Kirigami.Units.gridUnit * 13; elide: Text.ElideRight }

                Name { text: "Pen:" }
                Val { text: page.state === "none" ? "no pen seen yet" : page.state === "away" ? "out of range" : page.state === "hover" ? "hovering" : "touching the screen" }
                Name { text: "Tool:" }
                Val { text: page.tool }
                Name { text: "Pressure:" }
                RowLayout {
                    QQC2.ProgressBar { Layout.preferredWidth: Kirigami.Units.gridUnit * 10; from: 0; to: 1; value: page.pressure }
                    QQC2.Label { Layout.preferredWidth: Kirigami.Units.gridUnit * 9; text: Math.round(page.pressure * 100) + "%  (max " + Math.round(page.maxPressure * 100) + "%)" }
                }
                Name { text: "Tilt:" }
                Val { text: page.tiltSeen ? "X " + page.xTilt.toFixed(0) + "\u00b0   Y " + page.yTilt.toFixed(0) + "\u00b0" : "not reported" }
                Name { text: "Buttons now:" }
                RowLayout {
                    spacing: Kirigami.Units.smallSpacing
                    Repeater {
                        model: [{ n: "Barrel (side)", on: page.barrelDown }, { n: "Eraser (top)", on: page.rubberDown }]
                        delegate: Rectangle {
                            Layout.preferredWidth: Kirigami.Units.gridUnit * 6; Layout.preferredHeight: Kirigami.Units.gridUnit * 1.6; radius: 4
                            color: modelData.on ? Kirigami.Theme.highlightColor : "transparent"
                            border.color: Kirigami.Theme.disabledTextColor
                            QQC2.Label { anchors.centerIn: parent; text: modelData.n; color: modelData.on ? Kirigami.Theme.highlightedTextColor : Kirigami.Theme.textColor }
                        }
                    }
                }
            }

        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Kirigami.Units.gridUnit * 2
            ColumnLayout {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignTop
                RowLayout { Kirigami.Heading { level: 4; text: "Bluetooth pen" } }
                QQC2.Label {
                    Layout.fillWidth: true; wrapMode: Text.WordWrap
                    text: s.bluetooth.length === 0 ? "No paired pen found."
                          : s.bluetooth.map(d => d.name + ": " + (d.connected ? "connected" + (d.battery >= 0 ? ", battery " + d.battery + "%" : "") : "paired, not connected (press a pen button to wake it)")).join("\n")
                }
            }
            ColumnLayout {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignTop
                Kirigami.Heading { level: 4; text: "Stylus battery" }
                QQC2.CheckBox { QQC2.ToolTip.text: (typeof tips !== "undefined" && tips[text]) || ""; QQC2.ToolTip.visible: hovered && QQC2.ToolTip.text.length > 0; QQC2.ToolTip.delay: 500;
                    text: "Hide the fake stylus battery"
                    checked: s.filterInstalled
                    enabled: !bridge.busy
                    onToggled: bridge.stylusFilter(checked)
                }
                QQC2.Label {
                    Layout.fillWidth: true; wrapMode: Text.WordWrap; opacity: 0.6
                    font.pointSize: Kirigami.Theme.defaultFont.pointSize - 1
                    text: "The touchscreen advertises a pen battery that never carries data. A small HID-BPF filter hides it. Asks for your password; takes effect after a restart."
                }
            }
        }
        QQC2.Label {
            visible: s.fakeBattery.length > 0
            Layout.fillWidth: true; wrapMode: Text.WordWrap
            color: Kirigami.Theme.neutralTextColor
            text: "The fake battery is currently showing (" + s.fakeBattery.join(", ") + ")."
        }
    }

    // ---- result popup with a countdown ----
    QQC2.Dialog {
        id: restartDialog
        property int left: 20
        property bool ok: true
        property string detail: ""
        modal: true
        anchors.centerIn: QQC2.Overlay.overlay
        title: ok ? "Done" : "Could not change it"
        contentItem: ColumnLayout {
            spacing: Kirigami.Units.largeSpacing
            QQC2.Label {
                Layout.preferredWidth: Kirigami.Units.gridUnit * 22
                wrapMode: Text.WordWrap
                text: restartDialog.ok ? "Restart the tablet to apply the change. This window closes by itself in " + restartDialog.left + " s."
                                       : restartDialog.detail
            }
            QQC2.ProgressBar { visible: restartDialog.ok; Layout.fillWidth: true; from: 0; to: 20; value: restartDialog.left }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                QQC2.Button { QQC2.ToolTip.text: (typeof tips !== "undefined" && tips[text]) || ""; QQC2.ToolTip.visible: hovered && QQC2.ToolTip.text.length > 0; QQC2.ToolTip.delay: 500; text: restartDialog.ok ? "Later" : "Close"; onClicked: restartDialog.close() }
                QQC2.Button { QQC2.ToolTip.text: (typeof tips !== "undefined" && tips[text]) || ""; QQC2.ToolTip.visible: hovered && QQC2.ToolTip.text.length > 0; QQC2.ToolTip.delay: 500; visible: restartDialog.ok; text: "Restart now"; highlighted: true; icon.name: "system-reboot"; onClicked: { restartDialog.close(); bridge.restartNow() } }
            }
        }
        Timer { running: restartDialog.visible && restartDialog.ok; interval: 1000; repeat: true; onTriggered: { restartDialog.left--; if (restartDialog.left <= 0) restartDialog.close() } }
    }
    Connections {
        target: bridge
        function onStylusFilterDone(ok, out) {
            page.s = bridge.stylusInfo()
            restartDialog.ok = ok; restartDialog.detail = out; restartDialog.left = 20; restartDialog.open()
        }
    }
}
