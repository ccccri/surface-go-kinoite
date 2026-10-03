import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    id: page
    title: "Sensors and battery"
    property var s: bridge.sensors()
    property var m: ({ accel: [0, 0, 0], gyro: [0, 0, 0] })
    property var info: bridge.deviceInfo()
    property real lux: s.lux !== undefined ? s.lux : 0

    // light: the hub updates at 10 Hz, so ask about 8 times a second; the rest does not change fast
    Timer { interval: 120; running: page.visible; repeat: true; onTriggered: { const r = bridge.sensors(); if (r.lux !== undefined) page.lux = r.lux; page.s = r } }
    Timer { interval: 80; running: page.visible; repeat: true; onTriggered: { const r = bridge.motion(false, false, false); if (r.accel) page.m = r } }

    component Card: Rectangle {
        id: card
        property string heading
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
                Rectangle { width: 3; height: Kirigami.Units.gridUnit * 1.2; radius: 2; color: Kirigami.Theme.highlightColor }
                QQC2.Label { text: card.heading; font.bold: true; font.pointSize: Kirigami.Theme.defaultFont.pointSize + 1 }
            }
            ColumnLayout { id: body; Layout.fillWidth: true; spacing: Kirigami.Units.smallSpacing }
        }
    }
    component Axis: RowLayout {
        property string name
        property real value
        property real range: 10
        property string unit: ""
        Layout.fillWidth: true
        QQC2.Label { text: name; Layout.preferredWidth: Kirigami.Units.gridUnit * 1.2; font.bold: true }
        Rectangle {
            Layout.fillWidth: true; Layout.preferredHeight: Kirigami.Units.gridUnit * 0.9
            color: "transparent"; border.color: Kirigami.Theme.disabledTextColor; radius: 3
            Rectangle { x: parent.width / 2; width: 1; height: parent.height; color: Kirigami.Theme.disabledTextColor }
            Rectangle {
                x: value >= 0 ? parent.width / 2 : parent.width / 2 + Math.max(-1, value / range) * parent.width / 2
                width: Math.min(1, Math.abs(value) / range) * parent.width / 2
                height: parent.height; radius: 3; color: Kirigami.Theme.highlightColor
            }
        }
        QQC2.Label { text: value.toFixed(1) + " " + unit; Layout.preferredWidth: Kirigami.Units.gridUnit * 5; horizontalAlignment: Text.AlignRight }
    }
    component Row2: RowLayout {
        property string name
        property string value
        Layout.fillWidth: true
        QQC2.Label { text: name; opacity: 0.7; Layout.preferredWidth: Kirigami.Units.gridUnit * 10 }
        QQC2.Label { text: value; Layout.fillWidth: true; wrapMode: Text.WordWrap }
    }

    ColumnLayout {
        spacing: Kirigami.Units.largeSpacing
        Kirigami.Heading { level: 2; text: page.title }

        GridLayout {
            Layout.fillWidth: true
            columns: 1
            columnSpacing: Kirigami.Units.largeSpacing
            rowSpacing: Kirigami.Units.largeSpacing

            ColumnLayout {
                Layout.alignment: Qt.AlignTop
                Layout.fillWidth: true
                spacing: Kirigami.Units.largeSpacing
                Card {
                    heading: "Ambient light"
                    RowLayout {
                        Layout.fillWidth: true
                        QQC2.Label { text: Math.round(page.lux) + " lux"; font.bold: true; font.pointSize: Kirigami.Theme.defaultFont.pointSize + 4; Layout.preferredWidth: Kirigami.Units.gridUnit * 7 }
                        QQC2.ProgressBar { Layout.fillWidth: true; from: 0; to: 1; value: Math.min(1, Math.log(1 + page.lux) / Math.log(1 + 10000)) }
                    }
                    QQC2.Label {
                        Layout.fillWidth: true; wrapMode: Text.WordWrap; opacity: 0.6
                        font.pointSize: Kirigami.Theme.defaultFont.pointSize - 1
                        text: "Cover the top bezel with a finger to see it drop. The sensor hub reports 10 times a second and the bar is logarithmic, like the eye."
                    }
                }
                // ------------------------------------------------ motion numbers
                Card {
                    heading: "Motion sensors"
                    QQC2.Label { text: "Accelerometer (m/s², gravity is about 9.8)"; font.bold: true }
                    Axis { name: "X"; value: page.m.accel[0]; range: 10 }
                    Axis { name: "Y"; value: page.m.accel[1]; range: 10 }
                    Axis { name: "Z"; value: page.m.accel[2]; range: 10 }
                    RowLayout { QQC2.Label { text: "Gyroscope (degrees per second)"; font.bold: true; topPadding: Kirigami.Units.smallSpacing } }
                    Axis { name: "X"; value: page.m.gyro[0]; range: 180; unit: "°/s" }
                    Axis { name: "Y"; value: page.m.gyro[1]; range: 180; unit: "°/s" }
                    Axis { name: "Z"; value: page.m.gyro[2]; range: 180; unit: "°/s" }
                }
            }
        }

        GridLayout {
            Layout.fillWidth: true
            columns: page.width > Kirigami.Units.gridUnit * 40 ? 2 : 1
            columnSpacing: Kirigami.Units.largeSpacing
            rowSpacing: Kirigami.Units.largeSpacing

            // ------------------------------------------------ battery
            Card {
                heading: "Battery"
                Layout.alignment: Qt.AlignTop
                Row2 { name: "Charge"; value: s.battery ? s.battery.percent + "% (" + s.battery.status.toLowerCase() + ")" : "n/a" }
                QQC2.ProgressBar { Layout.fillWidth: true; from: 0; to: 100; value: s.battery ? s.battery.percent : 0 }
                Row2 { name: s.battery && s.battery.status === "Discharging" ? "Discharge power" : "Charging power"; value: s.battery && s.battery.watts !== undefined ? s.battery.watts + " W" : "n/a" }
                Row2 { name: s.battery && s.battery.status === "Charging" ? "Time to full" : "Time left"; value: s.battery && s.battery.hours !== undefined ? s.battery.hours + " h" : "n/a" }
                Row2 { name: "Health"; value: s.battery && s.battery.health ? s.battery.health + "% of the original capacity" : "n/a" }
                Row2 { name: "Charge cycles"; value: s.battery ? s.battery.cycles : "n/a" }
                QQC2.Label {
                    Layout.fillWidth: true; wrapMode: Text.WordWrap; opacity: 0.6
                    font.pointSize: Kirigami.Theme.defaultFont.pointSize - 1
                    text: "The power value is the instantaneous draw of the whole tablet; compare it with the screen off and on to see what costs most."
                }
            }

            // ------------------------------------------------ age and identity
            Card {
                heading: "About this tablet"
                Layout.alignment: Qt.AlignTop
                Row2 { name: "Model"; value: info.model }
                Row2 { name: "Firmware (UEFI)"; value: info.firmware + (info.firmwareDate ? ", dated " + info.firmwareDate : "") }
                Row2 { visible: info.display !== undefined; name: "Display"; value: info.display ? (info.display.name ? info.display.name + ", " : "") + "made in week " + info.display.week + " of " + info.display.year : "" }
                Row2 { visible: info.battery !== undefined; name: "Battery"; value: info.battery ? info.battery.maker + " " + info.battery.model + ", serial " + info.battery.serial + ", " + info.battery.now + " of " + info.battery.design + " mAh" : "" }
                Row2 { visible: info.storage !== undefined; name: "Storage"; value: info.storage ? (info.storage.model ? info.storage.model + ", " : "") + info.storage.size + " GB" : "" }
                Row2 { name: "Processor"; value: info.cpu + ", " + info.memory + " GB of memory" }
                Row2 { visible: info.installed !== ""; name: "This system installed"; value: info.installed }
                Row2 { name: "Kernel"; value: info.kernel }
                QQC2.Label {
                    Layout.fillWidth: true; wrapMode: Text.WordWrap; opacity: 0.6
                    font.pointSize: Kirigami.Theme.defaultFont.pointSize - 1
                    text: "The display's manufacture week is the best hint of the tablet's age: the firmware date is when Microsoft last built the UEFI, not when your unit was made."
                }
            }
        }
    }
}
