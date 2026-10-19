package org.pikaraoke.tv;

import android.app.*;
import android.widget.EditText;
import org.mozilla.geckoview.*;

/** Preserve the original web UI's alert, confirmation and text-input flows. */
final class RoomPrompts implements GeckoSession.PromptDelegate {
    private final Activity activity;
    RoomPrompts(Activity activity) { this.activity = activity; }
    @Override public GeckoResult<PromptResponse> onAlertPrompt(GeckoSession session, AlertPrompt prompt) {
        GeckoResult<PromptResponse> result = new GeckoResult<>();
        new AlertDialog.Builder(activity).setTitle(prompt.title).setMessage(prompt.message)
            .setPositiveButton("Close", (d,w) -> result.complete(prompt.dismiss()))
            .setOnCancelListener(d -> result.complete(prompt.dismiss())).show();
        return result;
    }
    @Override public GeckoResult<PromptResponse> onButtonPrompt(GeckoSession session, ButtonPrompt prompt) {
        GeckoResult<PromptResponse> result = new GeckoResult<>();
        new AlertDialog.Builder(activity).setTitle(prompt.title).setMessage(prompt.message)
            .setPositiveButton("Confirm", (d,w) -> result.complete(prompt.confirm(ButtonPrompt.Type.POSITIVE)))
            .setNegativeButton("Cancel", (d,w) -> result.complete(prompt.dismiss()))
            .setOnCancelListener(d -> result.complete(prompt.dismiss())).show();
        return result;
    }
    @Override public GeckoResult<PromptResponse> onTextPrompt(GeckoSession session, TextPrompt prompt) {
        GeckoResult<PromptResponse> result = new GeckoResult<>();
        EditText field = new EditText(activity); field.setSingleLine(); field.setText(prompt.defaultValue);
        new AlertDialog.Builder(activity).setTitle(prompt.title).setMessage(prompt.message).setView(field)
            .setPositiveButton("Continue", (d,w) -> result.complete(prompt.confirm(field.getText().toString())))
            .setNegativeButton("Cancel", (d,w) -> result.complete(prompt.dismiss()))
            .setOnCancelListener(d -> result.complete(prompt.dismiss())).show();
        return result;
    }
    @Override public GeckoResult<PromptResponse> onChoicePrompt(GeckoSession session, ChoicePrompt prompt) {
        GeckoResult<PromptResponse> result = new GeckoResult<>();
        java.util.List<ChoicePrompt.Choice> items = new java.util.ArrayList<>();
        flatten(prompt.choices, items);
        String[] labels = new String[items.size()];
        for (int i=0; i<items.size(); i++) labels[i] = items.get(i).label;
        AlertDialog.Builder dialog = new AlertDialog.Builder(activity).setTitle(prompt.title);
        if (prompt.type == ChoicePrompt.Type.MULTIPLE) {
            boolean[] checked = new boolean[items.size()];
            for (int i=0;i<items.size();i++) checked[i]=items.get(i).selected;
            dialog.setMultiChoiceItems(labels, checked, (d,i,on) -> checked[i]=on)
                .setPositiveButton("Choose", (d,w) -> {
                    java.util.List<ChoicePrompt.Choice> selected = new java.util.ArrayList<>();
                    for(int i=0;i<checked.length;i++) if(checked[i]) selected.add(items.get(i));
                    result.complete(prompt.confirm(selected.toArray(new ChoicePrompt.Choice[0])));
                });
        } else dialog.setItems(labels, (d,i) -> result.complete(prompt.confirm(items.get(i))));
        dialog.setNegativeButton("Cancel", (d,w) -> result.complete(prompt.dismiss()))
            .setOnCancelListener(d -> result.complete(prompt.dismiss())).show();
        return result;
    }
    private static void flatten(ChoicePrompt.Choice[] source, java.util.List<ChoicePrompt.Choice> target) {
        for(ChoicePrompt.Choice choice:source) {
            if(choice.disabled || choice.separator) continue;
            if(choice.items!=null) flatten(choice.items,target); else target.add(choice);
        }
    }
}
