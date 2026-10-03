import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    id: page
    title: "Updates and repair"
    property var u: bridge.updateInfo()

    ColumnLayout {
        Kirigami.Heading { level: 2; text: page.title }
        spacing: Kirigami.Units.largeSpacing

        Kirigami.InlineMessage {
            Layout.fillWidth: true
            visible: true
            type: u.builtNow ? Kirigami.MessageType.Positive : Kirigami.MessageType.Error
            text: u.builtNow ? "The patched drivers are built for the running kernel (" + u.kernel + ")."
                             : "The running kernel (" + u.kernel + ") has no patched drivers yet: the camera, NFC and volume fixes are off until you rebuild."
        }

        Kirigami.Heading { level: 3; text: "After a kernel update" }
        QQC2.Label {
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            text: "Kernel drivers are tied to one kernel version, so a kernel update needs a rebuild of the four patched drivers. It takes a few minutes, asks for the sudo password in a terminal window, and ends with a restart."
        }
        QQC2.Button { QQC2.ToolTip.text: (typeof tips !== "undefined" && tips[text]) || ""; QQC2.ToolTip.visible: hovered && QQC2.ToolTip.text.length > 0; QQC2.ToolTip.delay: 500;
            text: "Rebuild drivers and camera library..."
            icon.name: "system-software-update"
            onClicked: bridge.rebuild()
        }

        Kirigami.Heading { level: 3; text: "Camera service"; topPadding: Kirigami.Units.largeSpacing }
        QQC2.Label {
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            text: "If a camera does not show up or an app shows a green picture, restarting the camera service often fixes it. Open camera apps must be reopened."
        }
        RowLayout {
            QQC2.Button { QQC2.ToolTip.text: (typeof tips !== "undefined" && tips[text]) || ""; QQC2.ToolTip.visible: hovered && QQC2.ToolTip.text.length > 0; QQC2.ToolTip.delay: 500; text: "Restart camera service"; icon.name: "view-refresh"; enabled: !bridge.busy; onClicked: bridge.restartCameras() }
            QQC2.BusyIndicator { running: bridge.busy; visible: bridge.busy }
        }

        Kirigami.Heading { level: 3; text: "What is installed"; topPadding: Kirigami.Units.largeSpacing }
        Kirigami.FormLayout {
            Layout.fillWidth: true
            QQC2.Label { Kirigami.FormData.label: "Running kernel:"; text: u.kernel }
            QQC2.Label { Kirigami.FormData.label: "Drivers built for:"; text: u.built.length > 0 ? u.built.join(", ") : "none"; wrapMode: Text.WordWrap; Layout.maximumWidth: Kirigami.Units.gridUnit * 28 }
            QQC2.Label { Kirigami.FormData.label: "libcamera:"; text: u.libcamera }
            QQC2.Label { Kirigami.FormData.label: "Camera patches:"; text: u.patches.join(", "); wrapMode: Text.WordWrap; Layout.maximumWidth: Kirigami.Units.gridUnit * 28 }
        }
    }
}
