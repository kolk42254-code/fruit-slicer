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

    // When the app leaves the screen, tell the game (it pauses and turns the camera off) and pause the WebView.
    // When the app comes back, resume the WebView and tell the game (it turns the camera back on).
    @Override
    public void onStop() {
        super.onStop();
        WebView webView = getBridge() != null ? getBridge().getWebView() : null;
        if (webView != null) {
            webView.evaluateJavascript("window.__fsAppHidden&&window.__fsAppHidden(true)", null);
            webView.onPause();
        }
    }

    @Override
    public void onStart() {
        super.onStart();
        WebView webView = getBridge() != null ? getBridge().getWebView() : null;
        if (webView != null) {
            webView.onResume();
            webView.evaluateJavascript("window.__fsAppHidden&&window.__fsAppHidden(false)", null);
        }
    }
}
