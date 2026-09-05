import QtQuick
import QtQuick.Controls
import Quickshell
import qs.Commons
import qs.Ui
import "StatusModel.js" as StatusModel

BarWidget {
  id: root
  moduleName: "godhiraj.omaudit-status"

  property bool popupOpen: false
  property int selectedAction: 1
  property var waitingStatus: StatusModel.errorDocument("Waiting for Omaudit Status service")

  readonly property var guardService: bar?.shell?.serviceFor("godhiraj.omaudit-status")
  readonly property var hostBarConfig: bar ? bar.barConfig : null
  readonly property var statusDocument: guardService && guardService.status
    ? guardService.status : waitingStatus
  readonly property double nowMs: guardService ? guardService.nowMs : Date.now()
  readonly property int staleAfterSec: guardService ? guardService.staleAfterSec : 1050
  readonly property bool canRefresh: !!guardService && !guardService.scanning
  readonly property bool canReview: !!guardService && statusDocument.installed !== false
  readonly property string guardState: StatusModel.state(statusDocument, nowMs, staleAfterSec)
  readonly property string guardTone: StatusModel.tone(statusDocument, nowMs, staleAfterSec)
  readonly property string freshness: StatusModel.freshnessText(statusDocument,
    !!guardService && guardService.scanning, nowMs, staleAfterSec)
  readonly property string guardSummary: StatusModel.summary(statusDocument, nowMs, staleAfterSec)
    + "; " + freshness
  readonly property var totals: statusDocument && statusDocument.totals
    ? statusDocument.totals : StatusModel.zeroTotals()
  readonly property var visiblePlugins: StatusModel.visiblePlugins(statusDocument, 8)
  readonly property color foreground: bar ? bar.foreground : Color.popups.text
  readonly property color barForeground: bar ? bar.barForeground : Color.bar.text
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property color shieldColor: {
    var key = StatusModel.colorKey(statusDocument, nowMs, staleAfterSec)
    if (key === "green") return Color.pick("omaudit-status.clean", "#6fa35b")
    if (key === "amber") return Color.pick("omaudit-status.caution", "#d0a447")
    if (key === "red") return bar ? bar.urgent : Color.urgent
    return Color.muted
  }

  function configureService() {
    var service = guardService
    if (service && typeof service.configure === "function") service.configure(settings || {})
  }

  function refresh() {
    var service = guardService
    if (service && typeof service.refresh === "function") service.refresh()
  }

  function review() {
    var service = guardService
    if (service && typeof service.review === "function") service.review()
  }

  function open() { popupOpen = true }
  function close() { popupOpen = false }
  function toggle() { popupOpen = !popupOpen }
  readonly property bool opened: popupOpen

  function activateAction() {
    if (selectedAction === 0 && canRefresh) refresh()
    else if (selectedAction === 1 && canReview) review()
  }

  function scrollContent(delta) {
    scroller.contentY = Math.max(0, Math.min(Math.max(0, scroller.contentHeight - scroller.height),
      scroller.contentY + delta))
  }

  function revealAction() {
    if (selectedAction < 0) return
    var bottom = actionRow.y + actionRow.height
    if (bottom > scroller.contentY + scroller.height)
      scrollContent(bottom - scroller.height - scroller.contentY)
    else if (actionRow.y < scroller.contentY)
      scrollContent(actionRow.y - scroller.contentY)
  }

  function selectAction() {
    if (canRefresh && canReview) selectedAction = selectedAction === 0 ? 1 : 0
    else selectedAction = canRefresh ? 0 : (canReview ? 1 : -1)
    Qt.callLater(root.revealAction)
  }

  function installationInstructions() {
    Qt.openUrlExternally("https://github.com/omarchy-forge/omaudit")
  }

  implicitWidth: vertical ? barSize : button.implicitWidth
  implicitHeight: vertical ? button.implicitHeight : barSize

  onBarChanged: Qt.callLater(root.configureService)
  onSettingsChanged: Qt.callLater(root.configureService)
  onHostBarConfigChanged: Qt.callLater(root.configureService)
  onGuardServiceChanged: Qt.callLater(root.configureService)
  onCanRefreshChanged: if (popupOpen && (selectedAction < 0 || (selectedAction === 0 && !canRefresh))) selectAction()
  onCanReviewChanged: if (popupOpen && (selectedAction < 0 || (selectedAction === 1 && !canReview))) selectAction()
  onPopupOpenChanged: if (popupOpen) {
    selectedAction = canReview ? 1 : (canRefresh ? 0 : -1)
    refresh()
    Qt.callLater(root.revealAction)
  }
  Component.onCompleted: Qt.callLater(root.configureService)

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: "󰒃"
    foreground: root.shieldColor
    slotSize: Style.bar.statusSlot
    tooltipText: root.guardSummary

    onPressed: function(buttonCode) {
      if (buttonCode === Qt.MiddleButton || buttonCode === Qt.RightButton) root.refresh()
      else root.toggle()
    }
  }

  KeyboardPanel {
    id: popup
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.popupOpen
    focusTarget: keyCatcher
    contentWidth: popup.fittedContentWidth(Style.space(390))
    contentHeight: popup.fittedContentHeight(content.implicitHeight, Style.space(620))

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onCloseRequested: root.close()
      onMoveRequested: function(dx, dy) {
        if (dx !== 0 || dy !== 0) root.selectAction()
      }
      onTabRequested: function(direction) {
        root.selectAction()
      }
      onActivateRequested: root.activateAction()
      onTextKey: function(text) {
        if (text === "r" || text === "R") root.refresh()
        if ((text === "i" || text === "I") && root.statusDocument.installed === false)
          root.installationInstructions()
      }
      // Forward only scrolling keys to a separate item, preserving the host's
      // Keys.onPressed dispatcher for Escape, Tab, activation and arrows.
      Keys.forwardTo: [scrollKeys]
      Item {
        id: scrollKeys
        Keys.onPressed: function(event) {
          if (event.key === Qt.Key_PageDown) root.scrollContent(scroller.height * 0.8)
          else if (event.key === Qt.Key_PageUp) root.scrollContent(-scroller.height * 0.8)
          else if (event.key === Qt.Key_Home) root.scrollContent(-scroller.contentHeight)
          else if (event.key === Qt.Key_End) root.scrollContent(scroller.contentHeight)
          else { event.accepted = false; return }
          event.accepted = true
        }
      }

      Flickable {
        id: scroller
        anchors.fill: parent
        contentWidth: width
        contentHeight: content.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.VerticalFlick
        interactive: contentHeight > height
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        Column {
          id: content
          width: parent.width
          spacing: Style.space(12)

          PanelHero {
            width: parent.width
            title: "Omaudit Status"
            meta: root.guardSummary
            detail: root.guardService && root.guardService.scanning ? "Scanning" : "Review"
            foreground: root.foreground
            fontFamily: root.fontFamily
            iconOpacity: root.guardTone === "dim" ? 0.55 : 1.0
            iconComponent: Component {
              Text {
                text: "󰒃"
                textFormat: Text.PlainText
                color: root.shieldColor
                font.family: root.fontFamily
                font.pixelSize: Style.font.display
              }
            }
          }

          Text {
            width: parent.width
            text: root.statusDocument.installed === false
              ? "Omaudit is missing. Install Omaudit v0.1.0 or newer using its official instructions, then refresh."
              : (root.guardState === "error"
                ? "Capability and risk review is unavailable. Findings require human review."
              : "Capability and risk review only — changes require human review."
              )
            textFormat: Text.PlainText
            color: Qt.darker(root.foreground, 1.35)
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.Wrap
          }

          Text {
            visible: root.statusDocument.ok !== true
            width: parent.width
            text: StatusModel.displayText(root.statusDocument.error, 300)
            textFormat: Text.PlainText
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WrapAnywhere
          }

          Text {
            visible: root.statusDocument.installed === false
            width: parent.width
            text: "Official installation instructions (I): https://github.com/omarchy-forge/omaudit"
            textFormat: Text.PlainText
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            wrapMode: Text.WrapAnywhere
            MouseArea {
              anchors.fill: parent
              onClicked: root.installationInstructions()
            }
          }

          Text {
            width: parent.width
            text: root.guardService && root.guardService.includeBuiltins ? "All plugins" : "Third-party plugins"
            textFormat: Text.PlainText
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }

          Row {
            width: parent.width
            spacing: Style.space(12)

            Repeater {
              model: [
                { label: "Plugins", value: root.totals.plugins },
                { label: "Changed", value: root.totals.changed },
                { label: "Untracked", value: root.totals.notTracked },
                { label: "Composition", value: root.totals.compositionRisks },
                { label: "Worst", value: root.statusDocument.worstGrade || "—" }
              ]

              Column {
                required property var modelData
                width: (content.width - Style.space(48)) / 5
                spacing: Style.space(2)

                Text {
                  anchors.horizontalCenter: parent.horizontalCenter
                  text: parent.modelData.value
                  textFormat: Text.PlainText
                  color: root.foreground
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.subtitle
                  font.bold: true
                }
                Text {
                  anchors.horizontalCenter: parent.horizontalCenter
                  text: parent.modelData.label
                  textFormat: Text.PlainText
                  color: Qt.darker(root.foreground, 1.5)
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                }
              }
            }
          }

          Text {
            width: parent.width
            text: root.freshness + "\n" + (root.statusDocument.ok ? "Successful scan: " : "Last attempt: ")
              + StatusModel.scanTime(root.statusDocument)
            textFormat: Text.PlainText
            color: Qt.darker(root.foreground, 1.55)
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            wrapMode: Text.Wrap
          }

          PanelSeparator {
            visible: root.visiblePlugins.length > 0
            foreground: root.foreground
          }

          Column {
            width: parent.width
            spacing: Style.space(6)
            visible: root.visiblePlugins.length > 0

            Repeater {
              model: root.visiblePlugins

              BorderSurface {
                required property var modelData
                width: parent.width
                implicitHeight: pluginLabels.implicitHeight + Style.space(10)
                radius: Style.cornerRadius
                color: "transparent"
                borderSpec: Border.controlSpec("normal", root.foreground, Color.accent)

                Column {
                  id: pluginLabels
                  anchors.left: parent.left
                  anchors.right: parent.right
                  anchors.verticalCenter: parent.verticalCenter
                  anchors.leftMargin: Style.space(8)
                  anchors.rightMargin: Style.space(8)
                  spacing: Style.space(2)

                  Text {
                    width: parent.width
                    text: StatusModel.displayText(modelData.name || modelData.id, 200)
                    textFormat: Text.PlainText
                    color: root.foreground
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.bodySmall
                    font.bold: modelData.status !== "unchanged"
                    elide: Text.ElideRight
                  }
                  Text {
                    width: parent.width
                    text: "ID: " + StatusModel.displayText(modelData.id, 200)
                    textFormat: Text.PlainText
                    color: root.foreground
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                    wrapMode: Text.WrapAnywhere
                  }
                  Text {
                    width: parent.width
                    text: "Grade " + (modelData.grade || "—")
                    textFormat: Text.PlainText
                    color: root.foreground
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                  }
                  Text {
                    width: parent.width
                    text: modelData.composition.length > 0
                      ? "Composition risk needs review"
                      : (modelData.status === "changed" ? "Capability drift"
                        : (modelData.status === "not-tracked" ? "Baseline review needed" : "Unchanged"))
                    textFormat: Text.PlainText
                    color: modelData.status === "unchanged"
                      ? Qt.darker(root.foreground, 1.5) : root.shieldColor
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                    elide: Text.ElideRight
                  }
                }
              }
            }
          }

          Text {
            visible: root.totals.plugins > root.visiblePlugins.length
            width: parent.width
            text: "+ " + (root.totals.plugins - root.visiblePlugins.length) + " more plugins"
            textFormat: Text.PlainText
            color: Qt.darker(root.foreground, 1.5)
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }

          Row {
            id: actionRow
            anchors.right: parent.right
            spacing: Style.space(8)

            Button {
              text: "Refresh"
              iconText: "󰑐"
              foreground: root.foreground
              hasCursor: root.selectedAction === 0
              focusable: true
              enabled: root.canRefresh
              onHovered: function(isHovered) { if (isHovered) root.selectedAction = 0 }
              onClicked: root.refresh()
            }

            Button {
              text: "Review in terminal"
              iconText: "󰆍"
              foreground: root.foreground
              hasCursor: root.selectedAction === 1
              focusable: true
              enabled: root.canReview
              onHovered: function(isHovered) { if (isHovered) root.selectedAction = 1 }
              onClicked: root.review()
            }
          }
        }
      }
    }
  }
}
