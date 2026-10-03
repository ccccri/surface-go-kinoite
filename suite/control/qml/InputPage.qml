import QtQuick
import QtQuick.Window
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.Page {
    id: page
    title: "Keyboard cover"
    topPadding: Kirigami.Units.largeSpacing
    property bool attached: bridge.folioAttached()

    // the cover can be pulled off at any moment: look a few times a second while this page is open
    Timer { interval: 300; repeat: true; running: true; onTriggered: attached = bridge.folioAttached() }

    property bool testing: false
    Component.onCompleted: if (startTest) testing = true
    onTestingChanged: {
        bridge.blockShortcuts(testing)
        if (testing) applicationWindow().enterFullScreen()
        else applicationWindow().leaveFullScreen()
    }
    Component.onDestruction: if (testing) testing = false
    Timer { running: page.testing && keytestSeconds > 0; interval: keytestSeconds * 1000; onTriggered: page.testing = false }

    ColumnLayout {
        Kirigami.Heading { level: 2; text: page.title }
        visible: !page.testing
        spacing: Kirigami.Units.largeSpacing

        Kirigami.InlineMessage {
            Layout.fillWidth: true
            visible: true
            type: attached ? Kirigami.MessageType.Positive : Kirigami.MessageType.Information
            text: attached ? "Keyboard cover attached" : "Keyboard cover disconnected. Attach it to type and use the trackpad."
        }
        QQC2.Label {
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            text: "Sometimes the trackpad or the keys stop answering while the cover is still attached, typically after sleep. Re-detecting the cover is the software equivalent of unplugging it and attaching it again: it takes about 5 seconds and no password."
        }
        RowLayout {
            QQC2.Button { QQC2.ToolTip.text: (typeof tips !== "undefined" && tips[text]) || ""; QQC2.ToolTip.visible: hovered && QQC2.ToolTip.text.length > 0; QQC2.ToolTip.delay: 500;
                text: "Re-detect keyboard and trackpad"
                icon.name: "input-keyboard"
                enabled: !bridge.busy && attached
                onClicked: bridge.folioReset()
            }
            QQC2.BusyIndicator { running: bridge.busy; visible: bridge.busy }
        }
        QQC2.Label {
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            opacity: 0.6
            text: "A background watcher also does this by itself when the trackpad is missing after boot or resume. This button is for when the cover looks connected but is silent."
        }

        Kirigami.Heading { level: 3; text: "Keyboard and trackpad test"; topPadding: Kirigami.Units.gridUnit }
        QQC2.Label {
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            text: "Shows a keyboard in your layout (" + bridge.keyboardLayout() + ") whose keys light up as you press them, and a trackpad area for clicks, scrolling and pinch. The test goes full screen and turns Plasma's shortcuts off so that no key or click does anything else. Hold Esc for 1.5 seconds, or press Exit, to leave."
        }
        QQC2.Button { QQC2.ToolTip.text: (typeof tips !== "undefined" && tips[text]) || ""; QQC2.ToolTip.visible: hovered && QQC2.ToolTip.text.length > 0; QQC2.ToolTip.delay: 500;
            text: "Start the test"
            icon.name: "input-keyboard-virtual"
            onClicked: page.testing = true
        }
    }

    KeyboardTest {
        visible: page.testing
        anchors.fill: parent
        onExitRequested: page.testing = false
    }
}
