package io.github.kolk42254code.fruitslicer;

import android.os.Bundle;
import android.view.WindowManager;
import android.webkit.WebView;
import androidx.activity.OnBackPressedCallback;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {

    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // The game is played with the hand in the air, not by touching the screen, so keep the screen awake.
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);

        // Back button / back gesture: the game closes an open panel or pauses first (window.__fsBack returns true).
        // In the menu it returns false, and the app goes to the background like the Home button.
        getOnBackPressedDispatcher().addCallback(this, new OnBackPressedCallback(true) {
            @Override
            public void handleOnBackPressed() {
                WebView webView = getBridge() != null ? getBridge().getWebView() : null;
                if (webView == null) {
                    moveTaskToBack(true);
                    return;
                }
                webView.evaluateJavascript(
                    "(function(){try{return !!(window.__fsBack&&window.__fsBack());}catch(e){return false;}})()",
                    value -> {
                        if (!"true".equals(value)) {
                            moveTaskToBack(true);
                        }
                    }
                );
            }
        });
    }

    // Leaving the app (Home, Back in the menu, a call, another app): tell the game at once, so it pauses and
    // turns the camera off. Coming back: tell the game, so it turns the camera back on.
    @Override
    public void onPause() {
        super.onPause();
        tellGame(true);
    }

    @Override
    public void onResume() {
        super.onResume();
        tellGame(false);
    }

    // Not on screen any more: also pause the WebView itself (animations, page visibility).
    @Override
    public void onStop() {
        super.onStop();
        WebView webView = getBridge() != null ? getBridge().getWebView() : null;
        if (webView != null) {
            webView.onPause();
        }
    }

    @Override
    public void onStart() {
        super.onStart();
        WebView webView = getBridge() != null ? getBridge().getWebView() : null;
        if (webView != null) {
            webView.onResume();
        }
    }

    private void tellGame(boolean away) {
        WebView webView = getBridge() != null ? getBridge().getWebView() : null;
        if (webView != null) {
            webView.evaluateJavascript("window.__fsAppHidden&&window.__fsAppHidden(" + away + ")", null);
        }
    }
}
