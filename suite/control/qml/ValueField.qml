import QtQuick
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami

// A value shown like in a photo editor: click it and type a number. Accepts a decimal comma, a minus sign, a unit after the number
// and a percent sign (on a 0..1 control "50%" means 0.5). Out of range values are clamped, text that is not a number is refused.
QQC2.TextField {
    id: root
    property real value: 0
    property real from: 0
    property real to: 1
    property real step: 0.1
    property string unit: ""
    property var names: null
    signal committed(real v)

    readonly property int decimals: step >= 1 ? 0 : step >= 0.1 ? 1 : 2
    function display(v) {
        if (names) return names[Math.max(0, Math.min(names.length - 1, Math.round(v)))]
        const t = (v > 0 && from < 0 ? "+" : "") + v.toFixed(decimals)
        return unit.length > 0 && unit !== "level" ? t + " " + unit : t
    }
    // returns NaN when the text is not a number
    function parse(txt) {
        let s = txt.trim().replace(/−/g, "-").replace(",", ".")
        if (names) {
            const i = names.findIndex(n => n.toLowerCase() === s.toLowerCase())
            if (i >= 0) return i
        }
        const m = s.match(/^([+-]?\s*\d*\.?\d+)\s*(%?)/)
        if (!m) return NaN
        let v = parseFloat(m[1].replace(/\s+/g, ""))
        if (m[2] === "%" && unit !== "%" && Math.abs(to) <= 2 && Math.abs(from) <= 2) v = v / 100
        return v
    }
    function commit() {
        const v = parse(text)
        if (isNaN(v)) { text = display(value); return }
        const c = Math.max(from, Math.min(to, v))
        const r = Number(c.toFixed(Math.max(decimals, step < 1 ? 2 : 0)))
        text = display(r)
        committed(r)
    }

    text: display(value)
    onValueChanged: if (!activeFocus) text = display(value)
    horizontalAlignment: TextInput.AlignRight
    selectByMouse: true
    implicitWidth: Kirigami.Units.gridUnit * 5
    implicitHeight: Kirigami.Units.gridUnit * 1.7
    padding: 2
    leftPadding: 4
    rightPadding: 4
    background: Rectangle {
        radius: 3
        color: root.activeFocus ? Kirigami.Theme.backgroundColor : "transparent"
        border.width: root.activeFocus || root.hovered ? 1 : 0
        border.color: root.activeFocus ? Kirigami.Theme.highlightColor : Kirigami.Theme.disabledTextColor
    }
    onActiveFocusChanged: if (activeFocus) selectAll(); else text = display(value)
    onAccepted: { commit(); focus = false }
    Keys.onEscapePressed: { text = display(value); focus = false }
    // what can be typed, with examples: shown while hovering and while typing
    readonly property string example: {
        if (names) return "Type a level: " + names.join(", ") + " (or 0 to " + (names.length - 1) + ")"
        const mid = ((from + to) / 2)
        const e1 = Number(mid.toFixed(decimals)), e2 = Number((from + (to - from) * 0.25).toFixed(decimals))
        let t = "Type a number from " + from + " to " + to + ", e.g. " + e1 + " or " + e2 + (decimals > 0 ? " (a comma works too: " + String(e2).replace(".", ",") + ")" : "")
        if (unit === "%") t += ", or " + e1 + "%"
        else if (unit.length > 0 && unit !== "level") t += ", or with the unit: " + e1 + " " + unit
        else if (Math.abs(to) <= 2 && Math.abs(from) <= 2) t += ", or a percentage: " + Math.round((from + to) / 4 * 100) + "%"
        return t + ". Values outside the range are brought to the limit."
    }
    QQC2.ToolTip.text: example
    QQC2.ToolTip.visible: hovered || activeFocus
    QQC2.ToolTip.delay: activeFocus ? 0 : 700
}
