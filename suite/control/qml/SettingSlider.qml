import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

// One adjustment of the editor-like Cameras page: name, editable value, reset button, a touch-sized slider and a short explanation.
ColumnLayout {
    id: root
    property string label
    property string desc
    property real from: 0
    property real to: 1
    property real step: 0.1
    property real modelValue: 0
    property real defaultValue: 0
    property string unit: ""
    property var names: null
    property bool showHints: true
    property alias dragging: slider.pressed
    signal edited(real value)
    signal resetRequested()

    spacing: 0
    Layout.fillWidth: true
    onModelValueChanged: slider.value = modelValue

    RowLayout {
        Layout.fillWidth: true
        QQC2.Label { text: root.label; font.bold: true }
        Item { Layout.fillWidth: true }
        ValueField {
            value: slider.value
            from: root.from; to: root.to; step: root.step; unit: root.unit; names: root.names
            onCommitted: v => { slider.value = v; root.edited(v) }
        }
        QQC2.ToolButton {
            icon.name: "edit-undo"
            opacity: Math.abs(slider.value - root.defaultValue) > root.step / 2 ? 1 : 0
            enabled: opacity > 0
            display: QQC2.AbstractButton.IconOnly
            onClicked: { slider.value = root.defaultValue; root.resetRequested() }
            QQC2.ToolTip.text: "Back to the default"
            QQC2.ToolTip.visible: hovered
        }
    }
    QQC2.Slider {
        id: slider
        Layout.fillWidth: true
        Layout.preferredHeight: Kirigami.Units.gridUnit * 2
        from: root.from
        to: root.to
        stepSize: root.step
        snapMode: QQC2.Slider.SnapAlways
        value: root.modelValue
        onMoved: root.edited(value)
    }
    Item { Layout.preferredHeight: Kirigami.Units.smallSpacing }
    HoverHandler { id: hov }
    QQC2.ToolTip { visible: hov.hovered && root.desc.length > 0 && !slider.pressed; text: root.desc; delay: 500; timeout: 12000 }
}
