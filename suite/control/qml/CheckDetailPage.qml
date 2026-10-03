import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    id: page
    property var check: ({})
    title: check.name

    ColumnLayout {
        spacing: Kirigami.Units.largeSpacing

        Kirigami.Heading { level: 2; text: check.name }

        Kirigami.InlineMessage {
            Layout.fillWidth: true
            visible: true
            type: check.status === "ok" ? Kirigami.MessageType.Positive : check.status === "warn" ? Kirigami.MessageType.Warning : Kirigami.MessageType.Error
            text: (check.status === "ok" ? "Working" : check.status === "warn" ? "Needs a look" : "Not working") + (check.detail ? ": " + check.detail : "")
        }

        Kirigami.Heading { level: 3; text: "What it does"; visible: check.what.length > 0 }
        QQC2.Label { text: check.what; wrapMode: Text.WordWrap; Layout.fillWidth: true; visible: check.what.length > 0 }

        Kirigami.Heading { level: 3; text: "How it works"; visible: check.tech.length > 0 }
        QQC2.Label { text: check.tech; wrapMode: Text.WordWrap; Layout.fillWidth: true; visible: check.tech.length > 0 }

        Kirigami.Heading { level: 3; text: "If it is not working"; visible: check.fix.length > 0 }
        QQC2.Label { text: check.fix; wrapMode: Text.WordWrap; Layout.fillWidth: true; visible: check.fix.length > 0 }
    }
}
