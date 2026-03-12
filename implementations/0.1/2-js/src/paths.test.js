import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { derivePath } from "./paths.js";

describe("derivePath", () => {
  describe("memory", () => {
    it("no tags", () => {
      const result = derivePath("memory", { date: ["2025-01-15"] }, "IMG_4521.jpg");
      assert.equal(result, "memories/2025-01/IMG_4521.jpg");
    });

    it("with event", () => {
      const result = derivePath(
        "memory",
        { date: ["2025-01-15"], event: ["Hawaii Vacation"] },
        "IMG_4521.jpg",
      );
      assert.equal(result, "memories/2025-01/Hawaii Vacation/IMG_4521.jpg");
    });

    it("nested event", () => {
      const result = derivePath(
        "memory",
        { date: ["2025-01-15"], event: ["Hawaii Vacation:Snorkeling"] },
        "IMG_4521.jpg",
      );
      assert.equal(
        result,
        "memories/2025-01/Hawaii Vacation/Snorkeling/IMG_4521.jpg",
      );
    });

    it("with name", () => {
      const result = derivePath(
        "memory",
        { date: ["2025-01-15"], name: ["Sunset Over Ocean"] },
        "IMG_4521.jpg",
      );
      assert.equal(result, "memories/2025-01/Sunset Over Ocean.jpg");
    });

    it("event + name", () => {
      const result = derivePath(
        "memory",
        {
          date: ["2025-01-15"],
          event: ["Hawaii Vacation:Snorkeling"],
          name: ["Sunset Over Ocean"],
        },
        "IMG_4521.jpg",
      );
      assert.equal(
        result,
        "memories/2025-01/Hawaii Vacation/Snorkeling/Sunset Over Ocean.jpg",
      );
    });
  });

  describe("music", () => {
    it("full tags with track", () => {
      const result = derivePath(
        "music",
        {
          artist: ["Pink Floyd"],
          album: ["Dark Side of the Moon"],
          year: ["1973"],
          track: ["01"],
          name: ["Time"],
        },
        "time.flac",
      );
      assert.equal(
        result,
        "music/Pink Floyd/[1973] Dark Side of the Moon/01 - Time.flac",
      );
    });

    it("no track number", () => {
      const result = derivePath(
        "music",
        { artist: ["Pink Floyd"], name: ["Another Brick"] },
        "another-brick.mp3",
      );
      assert.equal(result, "music/Pink Floyd/Another Brick.mp3");
    });

    it("no tags", () => {
      const result = derivePath("music", {}, "track-01.mp3");
      assert.equal(result, "music/_unknown/track-01.mp3");
    });

    it("track padding", () => {
      const result = derivePath(
        "music",
        {
          artist: ["Pink Floyd"],
          album: ["The Wall"],
          year: ["1979"],
          track: ["5"],
          name: ["Another Brick"],
        },
        "test.flac",
      );
      assert.equal(
        result,
        "music/Pink Floyd/[1979] The Wall/05 - Another Brick.flac",
      );
    });
  });

  describe("movie", () => {
    it("standalone with year", () => {
      const result = derivePath(
        "movie",
        { name: ["The Dark Knight"], year: ["2008"] },
        "movie.mkv",
      );
      assert.equal(result, "movies/The Dark Knight [2008].mkv");
    });

    it("with series", () => {
      const result = derivePath(
        "movie",
        {
          series: ["Indiana Jones"],
          name: ["Raiders of the Lost Ark"],
          year: ["1981"],
        },
        "movie.mkv",
      );
      assert.equal(
        result,
        "movies/Indiana Jones/Raiders of the Lost Ark [1981].mkv",
      );
    });

    it("no tags", () => {
      const result = derivePath("movie", {}, "movie.mkv");
      assert.equal(result, "movies/movie.mkv");
    });
  });

  describe("tv", () => {
    it("full tags", () => {
      const result = derivePath(
        "tv",
        {
          show: ["The Office"],
          season: ["03"],
          episode: ["05"],
          name: ["The Merger"],
        },
        "episode.mkv",
      );
      assert.equal(result, "tv/The Office/Season 03/05 - The Merger.mkv");
    });
  });

  describe("podcast", () => {
    it("full tags", () => {
      const result = derivePath(
        "podcast",
        {
          show: ["Hardcore History"],
          episode: ["66"],
          name: ["Supernova in the East"],
        },
        "episode.mp3",
      );
      assert.equal(
        result,
        "podcast/Hardcore History/66 - Supernova in the East.mp3",
      );
    });
  });

  describe("book", () => {
    it("with series", () => {
      const result = derivePath(
        "book",
        {
          author: ["Tolkien"],
          series: ["Middle Earth"],
          name: ["The Hobbit"],
        },
        "book.m4a",
      );
      assert.equal(result, "books/Tolkien/Middle Earth/The Hobbit.m4a");
    });
  });

  describe("comedy", () => {
    it("full tags", () => {
      const result = derivePath(
        "comedy",
        { artist: ["John Mulaney"], name: ["Kid Gorgeous"], year: ["2018"] },
        "special.mp4",
      );
      assert.equal(result, "comedy/John Mulaney/[2018] Kid Gorgeous.mp4");
    });
  });
});
