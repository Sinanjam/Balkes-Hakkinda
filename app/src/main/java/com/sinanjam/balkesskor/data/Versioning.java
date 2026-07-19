package com.sinanjam.balkesskor.data;

import java.util.Locale;

public final class Versioning {
    private Versioning() { }

    public static boolean isNewer(String candidate, String current) {
        ParsedVersion left = parse(candidate);
        ParsedVersion right = parse(current);
        return left.valid && right.valid && compare(left, right) > 0;
    }

    public static String display(String raw) {
        String value = raw == null ? "" : raw.trim();
        if (value.startsWith("v") || value.startsWith("V")) value = value.substring(1);
        return value;
    }

    private static int compare(ParsedVersion left, ParsedVersion right) {
        for (int index = 0; index < left.numbers.length; index++) {
            int compared = Integer.compare(left.numbers[index], right.numbers[index]);
            if (compared != 0) return compared;
        }

        if (left.qualifier.length() == 0 && right.qualifier.length() > 0) return 1;
        if (left.qualifier.length() > 0 && right.qualifier.length() == 0) return -1;
        if (left.qualifier.equals(right.qualifier)) return 0;

        int rank = Integer.compare(qualifierRank(left.qualifier), qualifierRank(right.qualifier));
        if (rank != 0) return rank;
        int number = Integer.compare(qualifierNumber(left.qualifier), qualifierNumber(right.qualifier));
        if (number != 0) return number;
        return left.qualifier.compareTo(right.qualifier);
    }

    private static ParsedVersion parse(String raw) {
        String value = display(raw).toLowerCase(Locale.ROOT);
        int build = value.indexOf('+');
        if (build >= 0) value = value.substring(0, build);
        String qualifier = "";
        int separator = value.indexOf('-');
        if (separator >= 0) {
            qualifier = value.substring(separator + 1);
            value = value.substring(0, separator);
        }

        String[] parts = value.split("\\.");
        int[] numbers = new int[4];
        boolean valid = false;
        for (int index = 0; index < numbers.length && index < parts.length; index++) {
            String digits = leadingDigits(parts[index]);
            if (digits.length() == 0) continue;
            try {
                numbers[index] = Integer.parseInt(digits);
                valid = true;
            } catch (NumberFormatException ignored) {
                return new ParsedVersion(numbers, qualifier, false);
            }
        }
        return new ParsedVersion(numbers, qualifier, valid);
    }

    private static String leadingDigits(String value) {
        int end = 0;
        while (end < value.length() && Character.isDigit(value.charAt(end))) end++;
        return value.substring(0, end);
    }

    private static int qualifierRank(String value) {
        if (value.startsWith("dev") || value.startsWith("snapshot")) return 0;
        if (value.startsWith("alpha")) return 1;
        if (value.startsWith("beta")) return 2;
        if (value.startsWith("rc")) return 3;
        return 1;
    }

    private static int qualifierNumber(String value) {
        String digits = value.replaceAll("\\D+", "");
        if (digits.length() == 0) return 0;
        try {
            return Integer.parseInt(digits);
        } catch (NumberFormatException ignored) {
            return 0;
        }
    }

    private static final class ParsedVersion {
        final int[] numbers;
        final String qualifier;
        final boolean valid;

        ParsedVersion(int[] numbers, String qualifier, boolean valid) {
            this.numbers = numbers;
            this.qualifier = qualifier;
            this.valid = valid;
        }
    }
}
