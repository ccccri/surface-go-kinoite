import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    id: page
    title: "Patches and modules"

    function color(status) {
        return status === "ok" ? Kirigami.Theme.positiveTextColor
             : status === "warn" ? Kirigami.Theme.neutralTextColor
             : Kirigami.Theme.negativeTextColor
    }
    readonly property int failures: bridge.checks.filter(c => c.status === "fail").length
    readonly property int warnings: bridge.checks.filter(c => c.status === "warn").length

    ColumnLayout {
        spacing: Kirigami.Units.largeSpacing

        RowLayout {
            Layout.fillWidth: true
            Kirigami.Heading { level: 2; text: "Patches and modules"; Layout.fillWidth: true }
            QQC2.Button { QQC2.ToolTip.text: (typeof tips !== "undefined" && tips[text]) || ""; QQC2.ToolTip.visible: hovered && QQC2.ToolTip.text.length > 0; QQC2.ToolTip.delay: 500; text: "Check again"; icon.name: "view-refresh"; enabled: !bridge.busy; onClicked: bridge.refresh() }
        }

        Kirigami.InlineMessage {
            Layout.fillWidth: true
            visible: bridge.checks.length > 0
            type: page.failures > 0 ? Kirigami.MessageType.Error : page.warnings > 0 ? Kirigami.MessageType.Warning : Kirigami.MessageType.Positive
            text: page.failures > 0 ? page.failures + " fix(es) not working" : page.warnings > 0 ? page.warnings + " thing(s) to look at" : "Everything is working. Select an item to see what it does."
        }

        QQC2.BusyIndicator { running: bridge.busy; visible: bridge.busy; Layout.alignment: Qt.AlignHCenter }

        Repeater {
            model: bridge.checks
            delegate: ColumnLayout {
                Layout.fillWidth: true
                spacing: 0
                Kirigami.ListSectionHeader {
                    Layout.fillWidth: true
                    visible: index === 0 || bridge.checks[index - 1].group !== modelData.group
                    label: modelData.group
                }
                QQC2.ItemDelegate {
                    Layout.fillWidth: true
                    contentItem: RowLayout {
                        spacing: Kirigami.Units.largeSpacing
                        Rectangle { width: Kirigami.Units.gridUnit * 0.9; height: width; radius: width / 2; color: page.color(modelData.status) }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 0
                            QQC2.Label { text: modelData.name; font.bold: true; Layout.fillWidth: true; horizontalAlignment: Text.AlignLeft }
                            QQC2.Label { text: modelData.detail; visible: text.length > 0; opacity: 0.7; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        }
                        Kirigami.Icon { source: "go-next"; implicitWidth: Kirigami.Units.iconSizes.small; implicitHeight: implicitWidth; opacity: 0.5 }
                    }
                    onClicked: applicationWindow().pageStack.layers.push(Qt.resolvedUrl("CheckDetailPage.qml"), { check: modelData })
                }
            }
        }
    }
}
