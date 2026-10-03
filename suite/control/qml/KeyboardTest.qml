import QtQuick
import QtQuick.Window
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

// Full keyboard and trackpad test. Plasma shortcuts are blocked while it runs (the page does that); hold Esc to leave.
FocusScope {
    id: root
    signal exitRequested()

    property var labels: bridge.keyLabels()
    property var pressed: ({})
    property var seen: ({})
    property int seenCount: 0
    property string last: "Press any key"
    readonly property real unit: Math.max(18, Math.min(width / 15.4, height * 0.46 / 6.3))

    readonly property var names: ({
        1: "Esc", 14: "Backspace", 15: "Tab", 28: "Enter", 42: "Shift", 54: "Shift", 58: "Caps", 29: "Ctrl", 56: "Alt",
        100: "AltGr", 125: "Win", 57: "", 105: "←", 103: "↑", 106: "→", 108: "↓", 111: "Del",
        59: "F1", 60: "F2", 61: "F3", 62: "F4", 63: "F5", 64: "F6", 65: "F7", 66: "F8", 67: "F9", 68: "F10", 87: "F11", 88: "F12"
    })
    // [evdev code, width in key units]; code 0 = gap
    readonly property var rows: [
        [[1, 1.2], [59, 1], [60, 1], [61, 1], [62, 1], [63, 1], [64, 1], [65, 1], [66, 1], [67, 1], [68, 1], [87, 1], [88, 1], [111, 1.3]],
        [[41, 1], [2, 1], [3, 1], [4, 1], [5, 1], [6, 1], [7, 1], [8, 1], [9, 1], [10, 1], [11, 1], [12, 1], [13, 1], [14, 2]],
        [[15, 1.5], [16, 1], [17, 1], [18, 1], [19, 1], [20, 1], [21, 1], [22, 1], [23, 1], [24, 1], [25, 1], [26, 1], [27, 1], [28, 1.5]],
        [[58, 1.8], [30, 1], [31, 1], [32, 1], [33, 1], [34, 1], [35, 1], [36, 1], [37, 1], [38, 1], [39, 1], [40, 1], [43, 1]],
        [[42, 1.3], [86, 1], [44, 1], [45, 1], [46, 1], [47, 1], [48, 1], [49, 1], [50, 1], [51, 1], [52, 1], [53, 1], [54, 2.3]],
        [[29, 1.3], [125, 1.3], [56, 1.3], [57, 5.4], [100, 1.3], [105, 1], [103, 1], [108, 1], [106, 1]]
    ]
    // every row is stretched to the same total width (its widest key takes the difference), so the right edge is straight
    readonly property var rowsNorm: rows.map(r => {
        const total = r.reduce((a, k) => a + k[1], 0)
        let wi = 0
        r.forEach((k, i) => { if (k[1] > r[wi][1]) wi = i })
        return r.map((k, i) => [k[0], k[1] + (i === wi ? 15 - total : 0)])
    })
    readonly property int totalKeys: { let n = 0; rows.forEach(r => r.forEach(k => n++)); return n }

    function label(code) {
        if (names[code] !== undefined) return names[code]
        return labels[code] || ""
    }
    function mark(code, down) {
        const p = Object.assign({}, pressed)
        if (down) p[code] = true; else delete p[code]
        pressed = p
        if (down && !seen[code]) {
            const s = Object.assign({}, seen); s[code] = true; seen = s
            seenCount = Object.keys(seen).length
        }
    }

    Keys.onPressed: event => {
        const code = event.nativeScanCode - 8
        event.accepted = true
        if (event.isAutoRepeat) return
        mark(code, true)
        last = (label(code) || "key") + "   (code " + code + ", Qt key 0x" + event.key.toString(16) + ")"
        if (code === 1 || event.key === Qt.Key_Escape) exitTimer.restart()
    }
    Keys.onReleased: event => {
        const code = event.nativeScanCode - 8
        event.accepted = true
        if (event.isAutoRepeat) return
        mark(code, false)
        if (code === 1 || event.key === Qt.Key_Escape) exitTimer.stop()
    }
    Timer { id: exitTimer; interval: 1500; onTriggered: root.exitRequested() }
    // keys only arrive while this item has the keyboard focus: take it back if a click or the compositor moved it
    Timer { interval: 700; repeat: true; running: root.visible; onTriggered: if (!root.activeFocus) root.forceActiveFocus() }
    Component.onCompleted: forceActiveFocus()
    onVisibleChanged: if (visible) forceActiveFocus()

    ColumnLayout {
        anchors.fill: parent
        spacing: Kirigami.Units.largeSpacing

        RowLayout {
            Layout.fillWidth: true
            QQC2.Label {
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: "Keyboard test: Plasma shortcuts are off while this runs. Type on the keys; they light up and turn green once tested. Hold Esc for 1.5 seconds, or press the button, to leave."
                opacity: 0.8
            }
            QQC2.Button { QQC2.ToolTip.text: (typeof tips !== "undefined" && tips[text]) || ""; QQC2.ToolTip.visible: hovered && QQC2.ToolTip.text.length > 0; QQC2.ToolTip.delay: 500; text: "Exit test"; icon.name: "dialog-close"; onClicked: root.exitRequested() }
        }

        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: root.unit * 6.2
            Column {
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: root.unit * 0.08
                Repeater {
                    model: root.rowsNorm
                    delegate: Row {
                        id: keyRow
                        readonly property int rowIndex: index
                        spacing: root.unit * 0.08
                        Repeater {
                            model: modelData
                            delegate: Rectangle {
                                width: modelData[1] * root.unit - root.unit * 0.08
                                height: root.unit * (keyRow.rowIndex === 0 ? 0.8 : 1) - root.unit * 0.08
                                radius: root.unit * 0.12
                                readonly property bool down: root.pressed[modelData[0]] === true
                                readonly property bool tested: root.seen[modelData[0]] === true
                                color: down ? Kirigami.Theme.highlightColor
                                     : tested ? Qt.rgba(Kirigami.Theme.positiveTextColor.r, Kirigami.Theme.positiveTextColor.g, Kirigami.Theme.positiveTextColor.b, 0.35)
                                     : Kirigami.Theme.backgroundColor
                                border.width: 1
                                border.color: Kirigami.Theme.disabledTextColor
                                QQC2.Label {
                                    anchors.centerIn: parent
                                    text: root.label(modelData[0])
                                    font.pixelSize: root.unit * 0.36
                                    color: parent.down ? Kirigami.Theme.highlightedTextColor : Kirigami.Theme.textColor
                                }
                            }
                        }
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            QQC2.Label { text: "Last key: " + root.last; font.bold: true; Layout.fillWidth: true; elide: Text.ElideRight }
            QQC2.Label { text: root.seenCount + " keys tested" }
            QQC2.Button { QQC2.ToolTip.text: (typeof tips !== "undefined" && tips[text]) || ""; QQC2.ToolTip.visible: hovered && QQC2.ToolTip.text.length > 0; QQC2.ToolTip.delay: 500; text: "Reset"; icon.name: "edit-clear-all"; onClicked: { root.seen = ({}); root.seenCount = 0; root.last = "Press any key"; root.forceActiveFocus() } }
        }

        // ---- trackpad ----
        Rectangle {
            id: pad
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: Kirigami.Units.gridUnit * 8
            color: Kirigami.Theme.backgroundColor
            border.color: Kirigami.Theme.disabledTextColor
            radius: 6
            clip: true

            property real px: -1
            property real py: -1
            property var btn: ({})
            property int clicks: 0
            property int doubles: 0
            property real scrollX: 0
            property real scrollY: 0
            property real pinchScale: 1
            property real pinchAngle: 0

            QQC2.Label { anchors.horizontalCenter: parent.horizontalCenter; anchors.top: parent.top; anchors.topMargin: 6; text: "Trackpad and mouse test area: move, click, double-click, scroll with two fingers, pinch"; opacity: 0.6 }

            MouseArea {
                id: area
                anchors.fill: parent
                hoverEnabled: true
                acceptedButtons: Qt.AllButtons
                onPositionChanged: mouse => { pad.px = mouse.x; pad.py = mouse.y }
                onPressed: mouse => { const b = Object.assign({}, pad.btn); b[mouse.button] = true; pad.btn = b; pad.clicks++; root.forceActiveFocus() }
                onReleased: mouse => { const b = Object.assign({}, pad.btn); delete b[mouse.button]; pad.btn = b }
                onDoubleClicked: pad.doubles++
                onExited: { pad.px = -1 }
            }
            WheelHandler {
                acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
                onWheel: event => { pad.scrollX += event.angleDelta.x / 120; pad.scrollY += event.angleDelta.y / 120 }
            }
            PinchHandler {
                target: null
                onScaleChanged: pad.pinchScale = scale
                onRotationChanged: pad.pinchAngle = rotation
            }
            Rectangle {
                visible: pad.px >= 0
                x: pad.px - 8; y: pad.py - 8; width: 16; height: 16; radius: 8
                color: Object.keys(pad.btn).length > 0 ? Kirigami.Theme.negativeTextColor : Kirigami.Theme.highlightColor
            }
            Row {
                anchors.centerIn: parent
                spacing: Kirigami.Units.largeSpacing
                Repeater {
                    model: [{ n: "Left", b: Qt.LeftButton }, { n: "Middle", b: Qt.MiddleButton }, { n: "Right", b: Qt.RightButton }]
                    delegate: Rectangle {
                        width: Kirigami.Units.gridUnit * 5; height: Kirigami.Units.gridUnit * 2.4; radius: 4
                        color: pad.btn[modelData.b] ? Kirigami.Theme.highlightColor : "transparent"
                        border.color: Kirigami.Theme.disabledTextColor
                        QQC2.Label { anchors.centerIn: parent; text: modelData.n; color: pad.btn[modelData.b] ? Kirigami.Theme.highlightedTextColor : Kirigami.Theme.textColor }
                    }
                }
            }
            QQC2.Label {
                anchors.bottom: parent.bottom; anchors.left: parent.left; anchors.margins: 8
                text: "Pointer " + (pad.px >= 0 ? Math.round(pad.px) + ", " + Math.round(pad.py) : "-") + "    Clicks " + pad.clicks + "    Double " + pad.doubles
                      + "    Scroll x " + pad.scrollX.toFixed(1) + " y " + pad.scrollY.toFixed(1)
                      + "    Pinch " + pad.pinchScale.toFixed(2) + "x, " + Math.round(pad.pinchAngle) + "°"
            }
        }
    }
}
