import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import QtQuick.Dialogs
import org.kde.kirigami as Kirigami

// Ten-band parametric equaliser: a frequency response graph with a handle per band (drag: frequency and gain, wheel: Q, double click: on/off),
// the numbers of the selected band, pre-amplifier, speaker boost, and presets (built in, your own, imported from Equalizer APO / AutoEQ files).
ColumnLayout {
    id: ed
    property string output: "speaker"
    property var st: bridge.eqState()
    property var cur: st.sets[output]
    property int sel: 4
    property bool showHints: true
    property bool advanced: false
    readonly property var kindNames: ({ peak: "Peak", lowshelf: "Low shelf", highshelf: "High shelf", highpass: "High-pass (low cut)", lowpass: "Low-pass (high cut)" })
    readonly property real fmin: 20
    readonly property real fmax: 20000
    readonly property real dbRange: 15
    spacing: Kirigami.Units.smallSpacing

    Connections { target: bridge; function onEqChanged() { ed.st = bridge.eqState(); ed.cur = ed.st.sets[ed.output]; graph.requestPaint() } }
    onOutputChanged: { cur = st.sets[output]; graph.requestPaint() }

    function kindsFor(i) { return i === 0 ? ["peak", "lowshelf", "highpass"] : i === 9 ? ["peak", "highshelf", "lowpass"] : ["peak"] }
    function push() { bridge.setEq(output, cur); graph.requestPaint() }
    function setBand(i, key, value) {
        const c = JSON.parse(JSON.stringify(cur))
        c.bands[i][key] = value
        cur = c
        push()
    }
    function setTop(key, value) { const c = JSON.parse(JSON.stringify(cur)); c[key] = value; cur = c; push() }

    // ---- the same biquad maths as the filter chain (RBJ cookbook), for drawing ----
    function coef(b) {
        if (!b.on) return [1, 0, 0, 1, 0, 0]
        const f = Math.min(b.freq, 24000 * 0.98), q = Math.max(0.1, b.q), g = b.gain
        if ((b.type === "peak" || b.type === "lowshelf" || b.type === "highshelf") && Math.abs(g) < 1e-4) return [1, 0, 0, 1, 0, 0]
        const A = Math.pow(10, g / 40), w = 2 * Math.PI * f / 48000, cw = Math.cos(w), al = Math.sin(w) / (2 * q)
        if (b.type === "peak") return [1 + al * A, -2 * cw, 1 - al * A, 1 + al / A, -2 * cw, 1 - al / A]
        const s = 2 * Math.sqrt(A) * al
        if (b.type === "lowshelf") return [A * ((A + 1) - (A - 1) * cw + s), 2 * A * ((A - 1) - (A + 1) * cw), A * ((A + 1) - (A - 1) * cw - s), (A + 1) + (A - 1) * cw + s, -2 * ((A - 1) + (A + 1) * cw), (A + 1) + (A - 1) * cw - s]
        if (b.type === "highshelf") return [A * ((A + 1) + (A - 1) * cw + s), -2 * A * ((A - 1) + (A + 1) * cw), A * ((A + 1) + (A - 1) * cw - s), (A + 1) - (A - 1) * cw + s, 2 * ((A - 1) - (A + 1) * cw), (A + 1) - (A - 1) * cw - s]
        if (b.type === "lowpass") return [(1 - cw) / 2, 1 - cw, (1 - cw) / 2, 1 + al, -2 * cw, 1 - al]
        if (b.type === "highpass") return [(1 + cw) / 2, -(1 + cw), (1 + cw) / 2, 1 + al, -2 * cw, 1 - al]
        return [1, 0, 0, 1, 0, 0]
    }
    function responseDb(freq) {
        const w = 2 * Math.PI * freq / 48000
        let total = 0
        for (const b of cur.bands) {
            const c = coef(b)
            const num = c[0] * c[0] + c[1] * c[1] + c[2] * c[2] + 2 * (c[0] * c[1] + c[1] * c[2]) * Math.cos(w) + 2 * c[0] * c[2] * Math.cos(2 * w)
            const den = c[3] * c[3] + c[4] * c[4] + c[5] * c[5] + 2 * (c[3] * c[4] + c[4] * c[5]) * Math.cos(w) + 2 * c[3] * c[5] * Math.cos(2 * w)
            total += 10 * Math.log10(Math.max(num, 1e-30) / Math.max(den, 1e-30))
        }
        return total + cur.preamp
    }
    function fToX(f) { return Math.log(f / fmin) / Math.log(fmax / fmin) * graph.width }
    function xToF(x) { return fmin * Math.pow(fmax / fmin, Math.max(0, Math.min(1, x / graph.width))) }
    function gToY(g) { return graph.height / 2 - g / dbRange * graph.height / 2 }
    function yToG(y) { return (graph.height / 2 - y) / (graph.height / 2) * dbRange }
    function nearest(x, y) {
        let best = -1, bd = 22
        cur.bands.forEach((b, i) => {
            const by = (b.type === "highpass" || b.type === "lowpass") ? gToY(0) : gToY(b.gain)
            const d = Math.hypot(fToX(b.freq) - x, by - y)
            if (d < bd) { bd = d; best = i }
        })
        return best
    }

    property string delName: ""
    property bool delBuiltin: false
    QQC2.Dialog {
        id: deleteDlg
        width: Kirigami.Units.gridUnit * 28
        modal: true
        anchors.centerIn: QQC2.Overlay.overlay
        title: ed.delBuiltin ? "Delete a default preset?" : "Delete preset?"
        standardButtons: QQC2.Dialog.Yes | QQC2.Dialog.No
        contentItem: QQC2.Label {
            width: parent ? parent.width : 0
            wrapMode: Text.WordWrap
            text: ed.delBuiltin ? "You are deleting the default preset \"" + ed.delName + "\". The only way to get it back is to apply the patches again (run the install script); your own presets are kept." : "Delete the preset \"" + ed.delName + "\"? This cannot be undone."
        }
        onAccepted: bridge.deleteEqPreset(ed.delName)
    }

    // ---- presets row ----
    RowLayout {
        Layout.fillWidth: true
        spacing: Kirigami.Units.smallSpacing
        QQC2.ComboBox {
            id: presetBox
            Layout.fillWidth: true
            model: ed.st.presets.map(p => p.name + (p.builtin ? "" : "  (custom)"))
        }
        QQC2.Button { QQC2.ToolTip.text: (typeof tips !== "undefined" && tips[text]) || ""; QQC2.ToolTip.visible: hovered && QQC2.ToolTip.text.length > 0; QQC2.ToolTip.delay: 500; text: "Apply"; icon.name: "dialog-ok-apply"; onClicked: bridge.applyEqPreset(ed.output, ed.st.presets[presetBox.currentIndex].name) }
        QQC2.Button { QQC2.ToolTip.text: (typeof tips !== "undefined" && tips[text]) || ""; QQC2.ToolTip.visible: hovered && QQC2.ToolTip.text.length > 0; QQC2.ToolTip.delay: 500; text: "Save as..."; icon.name: "document-save-as"; onClicked: { eqName.text = ""; eqNameDialog.open(); eqName.forceActiveFocus() } }
        QQC2.Button {
            icon.name: "edit-delete"
            enabled: presetBox.currentIndex >= 0 && ed.st.presets.length > 0
            onClicked: { delName = ed.st.presets[presetBox.currentIndex].name; delBuiltin = ed.st.presets[presetBox.currentIndex].builtin; deleteDlg.open() }
            QQC2.ToolTip.text: "Delete the selected preset"; QQC2.ToolTip.visible: hovered
        }
    }
    RowLayout {
        visible: ed.advanced
        Layout.fillWidth: true
        spacing: Kirigami.Units.smallSpacing
        QQC2.Button { QQC2.ToolTip.text: (typeof tips !== "undefined" && tips[text]) || ""; QQC2.ToolTip.visible: hovered && QQC2.ToolTip.text.length > 0; QQC2.ToolTip.delay: 500; text: "Import file..."; icon.name: "document-import"; onClicked: importDialog.open() }
        QQC2.Button { QQC2.ToolTip.text: (typeof tips !== "undefined" && tips[text]) || ""; QQC2.ToolTip.visible: hovered && QQC2.ToolTip.text.length > 0; QQC2.ToolTip.delay: 500; text: "Export..."; icon.name: "document-export"; onClicked: exportDialog.open() }
        QQC2.Button { QQC2.ToolTip.text: (typeof tips !== "undefined" && tips[text]) || ""; QQC2.ToolTip.visible: hovered && QQC2.ToolTip.text.length > 0; QQC2.ToolTip.delay: 500; text: "Reset to flat"; icon.name: "edit-undo"; onClicked: bridge.applyEqPreset(ed.output, "Flat") }
        Item { Layout.fillWidth: true }
    }
    QQC2.Label {
        visible: ed.showHints && ed.advanced
        Layout.fillWidth: true; wrapMode: Text.WordWrap; opacity: 0.6
        font.pointSize: Kirigami.Theme.defaultFont.pointSize - 1
        text: "Drag a dot to set its frequency (left-right) and gain (up-down); scroll over the graph to make the selected band wider or narrower (Q); double-click a dot to switch it off. Files in the Equalizer APO / AutoEQ text format (\"Preamp: -6 dB\", \"Filter 1: ON PK Fc 105 Hz Gain -2.5 dB Q 0.70\") can be imported: AutoEQ (github.com/jaakkopasanen/AutoEq) has free ones for hundreds of headphones."
    }

    // ---- the graph ----
    Canvas {
        id: graph
        visible: ed.advanced
        Layout.fillWidth: true
        Layout.preferredHeight: Kirigami.Units.gridUnit * 15
        antialiasing: true
        onWidthChanged: requestPaint()
        onPaint: {
            const c = getContext("2d")
            c.clearRect(0, 0, width, height)
            const txt = Kirigami.Theme.textColor, dim = Qt.rgba(txt.r, txt.g, txt.b, 0.18), lab = Qt.rgba(txt.r, txt.g, txt.b, 0.55)
            c.fillStyle = Qt.rgba(txt.r, txt.g, txt.b, 0.05); c.fillRect(0, 0, width, height)
            c.strokeStyle = dim; c.lineWidth = 1; c.fillStyle = lab; c.font = "10px sans-serif"
            for (const f of [20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000]) {
                const x = ed.fToX(f); c.beginPath(); c.moveTo(x, 0); c.lineTo(x, height); c.stroke()
                c.fillText(f >= 1000 ? (f / 1000) + "k" : f, Math.min(x + 3, width - 22), height - 4)
            }
            for (const g of [-12, -6, 0, 6, 12]) {
                const y = ed.gToY(g); c.strokeStyle = g === 0 ? lab : dim; c.beginPath(); c.moveTo(0, y); c.lineTo(width, y); c.stroke()
                c.fillText((g > 0 ? "+" : "") + g + " dB", 4, y - 3)
            }
            // response
            const hl = Kirigami.Theme.highlightColor
            c.beginPath()
            for (let x = 0; x <= width; x += 2) {
                const y = Math.max(0, Math.min(height, ed.gToY(ed.responseDb(ed.xToF(x)))))
                if (x === 0) c.moveTo(x, y); else c.lineTo(x, y)
            }
            c.strokeStyle = hl; c.lineWidth = 2.5; c.stroke()
            c.lineTo(width, ed.gToY(0)); c.lineTo(0, ed.gToY(0)); c.closePath()
            c.fillStyle = Qt.rgba(hl.r, hl.g, hl.b, 0.16); c.fill()
            // handles
            ed.cur.bands.forEach((b, i) => {
                const x = ed.fToX(b.freq), y = (b.type === "highpass" || b.type === "lowpass") ? ed.gToY(0) : ed.gToY(b.gain)
                c.beginPath(); c.arc(x, y, i === ed.sel ? 11 : (i === graph.hover ? 10 : 8), 0, 2 * Math.PI)
                c.fillStyle = b.on ? (i === ed.sel ? hl : Kirigami.Theme.backgroundColor) : Qt.rgba(txt.r, txt.g, txt.b, 0.2)
                c.fill(); c.lineWidth = 2; c.strokeStyle = b.on ? hl : lab; c.stroke()
                c.fillStyle = b.on && i === ed.sel ? Kirigami.Theme.highlightedTextColor : lab; c.font = "9px sans-serif"
                c.fillText(String(i + 1), x - 3, y + 3)
            })
        }
        // Pointer handlers instead of a MouseArea: a drag that starts on a band is taken over from the scrolling page, so a finger can move the dots
        // without the page moving. A band is picked by its position along the frequency axis (and the closest dot in height), not by hitting the dot exactly.
        property int drag: -1
        property int hover: -1
        function pick(x, y) {
            let best = -1, bd = 1e9
            ed.cur.bands.forEach((b, i) => {
                const dx = Math.abs(ed.fToX(b.freq) - x)
                if (dx > 34) return
                const by = (b.type === "highpass" || b.type === "lowpass") ? ed.gToY(0) : ed.gToY(b.gain)
                const d = dx + Math.abs(by - y) * 0.6
                if (d < bd) { bd = d; best = i }
            })
            return best
        }
        HoverHandler {
            id: hov
            cursorShape: graph.hover >= 0 ? Qt.OpenHandCursor : Qt.ArrowCursor
            onPointChanged: { const h = graph.pick(point.position.x, point.position.y); if (h !== graph.hover) { graph.hover = h; graph.requestPaint() } }
            onHoveredChanged: if (!hovered) { graph.hover = -1; graph.requestPaint() }
        }
        DragHandler {
            id: dh
            target: null
            grabPermissions: PointerHandler.CanTakeOverFromAnything
            xAxis.enabled: true
            yAxis.enabled: true
            onActiveChanged: {
                if (active) { const i = graph.pick(centroid.pressPosition.x, centroid.pressPosition.y); graph.drag = i; if (i >= 0) { ed.sel = i; graph.requestPaint() } }
                else graph.drag = -1
            }
            onCentroidChanged: {
                if (!active || graph.drag < 0) return
                const b = ed.cur.bands[graph.drag]
                const c = JSON.parse(JSON.stringify(ed.cur))
                c.bands[graph.drag].freq = Math.round(ed.xToF(Math.max(0, Math.min(graph.width, centroid.position.x))))
                if (b.type !== "highpass" && b.type !== "lowpass") c.bands[graph.drag].gain = Math.round(Math.max(-24, Math.min(24, ed.yToG(centroid.position.y))) * 10) / 10
                ed.cur = c; ed.push()
            }
        }
        TapHandler {
            gesturePolicy: TapHandler.ReleaseWithinBounds
            onTapped: (eventPoint, button) => { const i = graph.pick(eventPoint.position.x, eventPoint.position.y); if (i >= 0) { ed.sel = i; graph.requestPaint() } }
            onDoubleTapped: (eventPoint, button) => { const i = graph.pick(eventPoint.position.x, eventPoint.position.y); if (i >= 0) ed.setBand(i, "on", !ed.cur.bands[i].on) }
        }
        WheelHandler {
            onWheel: wheel => {
                const q = ed.cur.bands[ed.sel].q * (wheel.angleDelta.y > 0 ? 1.12 : 1 / 1.12)
                ed.setBand(ed.sel, "q", Math.round(Math.max(0.1, Math.min(20, q)) * 100) / 100)
            }
        }
    }

    // ---- the selected band ----
    RowLayout {
        visible: ed.advanced
        Layout.fillWidth: true
        spacing: Kirigami.Units.smallSpacing
        QQC2.Label { text: "Band " + (ed.sel + 1); font.bold: true }
        QQC2.ComboBox {
            Layout.preferredWidth: Kirigami.Units.gridUnit * 11
            model: ed.kindsFor(ed.sel).map(k => ed.kindNames[k])
            currentIndex: Math.max(0, ed.kindsFor(ed.sel).indexOf(ed.cur.bands[ed.sel].type))
            enabled: ed.kindsFor(ed.sel).length > 1
            onActivated: i => ed.setBand(ed.sel, "type", ed.kindsFor(ed.sel)[i])
        }
        Item { Layout.fillWidth: true }
        QQC2.Switch { QQC2.ToolTip.text: (typeof tips !== "undefined" && tips[text]) || ""; QQC2.ToolTip.visible: hovered && QQC2.ToolTip.text.length > 0; QQC2.ToolTip.delay: 500; text: "On"; checked: ed.cur.bands[ed.sel].on; onToggled: ed.setBand(ed.sel, "on", checked) }
    }
    GridLayout {
        visible: ed.advanced
        Layout.fillWidth: true
        columns: 3
        columnSpacing: Kirigami.Units.largeSpacing
        QQC2.Label { text: "Frequency"; opacity: 0.7 }
        QQC2.Label { text: "Gain"; opacity: 0.7; visible: ed.cur.bands[ed.sel].type !== "highpass" && ed.cur.bands[ed.sel].type !== "lowpass" }
        QQC2.Label { text: "Q (width)"; opacity: 0.7 }
        ValueField { from: 20; to: 20000; step: 1; unit: "Hz"; value: ed.cur.bands[ed.sel].freq; onCommitted: v => ed.setBand(ed.sel, "freq", v) }
        ValueField { from: -24; to: 24; step: 0.1; unit: "dB"; value: ed.cur.bands[ed.sel].gain; visible: ed.cur.bands[ed.sel].type !== "highpass" && ed.cur.bands[ed.sel].type !== "lowpass"; onCommitted: v => ed.setBand(ed.sel, "gain", v) }
        ValueField { from: 0.1; to: 20; step: 0.01; value: ed.cur.bands[ed.sel].q; onCommitted: v => ed.setBand(ed.sel, "q", v) }
    }

    SettingSlider {
        visible: ed.advanced
        label: "Pre-amplifier"
        desc: "Lowers or raises everything before the bands. When you boost a band, lower this by about the same amount so that loud music does not distort."
        showHints: ed.showHints
        from: -24; to: 12; step: 0.5; unit: "dB"; defaultValue: 0
        modelValue: ed.cur.preamp
        onEdited: v => ed.setTop("preamp", v)
        onResetRequested: ed.setTop("preamp", 0)
    }
    SettingSlider {
        label: "Speaker boost"
        desc: "How much louder than the plain volume this output is driven. With 120 the desktop volume at 100% sounds like 120% would on a plain speaker (the Surface Go speakers are quiet). Above about 150 the sound starts to distort."
        showHints: ed.showHints
        from: 100; to: 180; step: 1; unit: "%"; defaultValue: ed.output === "speaker" ? 120 : 100
        modelValue: ed.cur.boost
        onEdited: v => ed.setTop("boost", v)
        onResetRequested: ed.setTop("boost", ed.output === "speaker" ? 120 : 100)
    }

    QQC2.Dialog {
        id: eqNameDialog
        modal: true
        anchors.centerIn: QQC2.Overlay.overlay
        title: "Save this equalizer as a preset"
        standardButtons: QQC2.Dialog.Ok | QQC2.Dialog.Cancel
        contentItem: QQC2.TextField { id: eqName; implicitWidth: Kirigami.Units.gridUnit * 18; placeholderText: "Preset name"; onAccepted: eqNameDialog.accept() }
        onAccepted: { const r = bridge.saveEqPreset(eqName.text, ed.cur); if (r !== "ok") bridge.notify("Please type a name that is not one of the built-in presets.") }
    }
    FileDialog {
        id: importDialog
        title: "Import an equalizer file"
        nameFilters: ["Equalizer APO / AutoEQ text (*.txt)", "All files (*)"]
        onAccepted: {
            const r = bridge.importEq(ed.output, selectedFile.toString())
            bridge.notify(r.ok ? "Imported " + r.bands + " bands." + (r.notes.length ? " " + r.notes.join("; ") : "") : "Could not import: " + r.notes.join("; "))
        }
    }
    FileDialog {
        id: exportDialog
        title: "Export the equalizer"
        fileMode: FileDialog.SaveFile
        defaultSuffix: "txt"
        nameFilters: ["Equalizer APO / AutoEQ text (*.txt)"]
        onAccepted: bridge.notify(bridge.exportEq(ed.output, selectedFile.toString()).ok ? "Exported." : "Could not write the file.")
    }
}
